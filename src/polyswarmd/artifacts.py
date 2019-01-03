import json
import logging
import re

import base58
from flask import current_app as app, g, Blueprint, request

from polyswarmd.response import success, failure

logger = logging.getLogger(__name__)
artifacts = Blueprint('artifacts', __name__)

# 100MB limit
# TODO: Should this be configurable in config file?
MAX_ARTIFACT_SIZE_REGULAR = 32 * 1024 * 1024
MAX_ARTIFACT_SIZE_ANONYMOUS = 2 * 1024 * 1024


def is_valid_ipfshash(ipfshash):
    """
    :param ipfshash:
    :return:
    """
    # TODO: Further multihash validation
    try:
        return len(ipfshash) < 100 and base58.b58decode(ipfshash)
    except Exception:
        return False


def list_artifacts(ipfshash):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    r = None
    try:
        stat_future = session.get(config.ipfs_uri + '/api/v0/object/stat', params={'arg': ipfshash})
        ls_future = session.get(config.ipfs_uri + '/api/v0/ls', params={'arg': ipfshash}, timeout=1)

        r = stat_future.result()
        r.raise_for_status()
        stats = r.json()

        r = ls_future.result()
        r.raise_for_status()
        ls = r.json()
    except Exception:
        logger.exception('Received error listing files from IPFS, got response: %s',
                         r.content if r is not None else 'None')
        return failure('Could not locate IPFS resource', 400)

    if stats.get('NumLinks', 0) == 0:
        return [('', stats.get('Hash', ''), stats.get('DataSize'))]

    objects = ls.get('Objects', [])
    if objects:
        links = [(l.get('Name', ''), l.get('Hash', ''), l.get('Size', 0)) for l in objects[0].get('Links', [])]

        if not links:
            links = [('', stats.get('Hash', ''), stats.get('DataSize', 0))]

        return links

    return []


@artifacts.route('/status', methods=['GET'])
def get_artifacts_status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    r = None
    try:
        future = session.get(config.ipfs_uri + '/api/v0/diag/sys', timeout=1)
        r = future.result()
        r.raise_for_status()
    except Exception:
        logger.exception('Received error connecting to IPFS, got response: %s', r.content if r is not None else 'None')
        return failure('Could not connect to IPFS', 500)

    online = r.json()['net']['online']
    return success({'online': online})


@artifacts.route('', methods=['POST'])
def post_artifacts():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    files = [('file', (f.filename, f, 'application/octet-stream')) for f in request.files.getlist(key='file')]
    if not files:
        return failure('No artifacts', 400)
    if len(files) > 256:
        return failure('Too many artifacts', 400)

    r = None
    try:
        future = session.post(
            config.ipfs_uri + '/api/v0/add',
            files=files,
            params={'wrap-with-directory': True})
        r = future.result()
        r.raise_for_status()
    except Exception:
        logger.exception('Received error posting to IPFS got response: %s', r.content if r is not None else 'None')
        return failure('Could not add artifacts to IPFS', 400)

    ipfshash = json.loads(r.text.splitlines()[-1])['Hash']
    return success(ipfshash)


@artifacts.route('/<ipfshash>', methods=['GET'])
def get_artifacts_ipfshash(ipfshash):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    arts = list_artifacts(ipfshash)
    if not arts:
        return failure('Could not locate IPFS resource', 404)
    if len(arts) > 256:
        return failure('Invalid IPFS resource, too many links', 400)

    return success([{'name': a[0], 'hash': a[1]} for a in arts])


@artifacts.route('/<ipfshash>/<int:id_>', methods=['GET'])
def get_artifacts_ipfshash_id(ipfshash, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    arts = list_artifacts(ipfshash)
    if not arts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(arts):
        return failure('Could not locate artifact ID', 404)

    _, artifact, size = arts[id_]
    if size > g.user.max_artifact_size:
        return failure('Artifact size greater than maximum allowed')

    r = None
    try:
        future = session.get(config.ipfs_uri + '/api/v0/cat', params={'arg': artifact}, timeout=1)
        r = future.result()
        r.raise_for_status()
    except Exception:
        logger.exception('Received error retrieving files from IPFS, got response: %s',
                         r.content if r is not None else 'None')
        return failure('Could not locate IPFS resource', 404)

    return r.content


@artifacts.route('/<ipfshash>/<int:id_>/stat', methods=['GET'])
def get_artifacts_ipfshash_id_stat(ipfshash, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    arts = list_artifacts(ipfshash)
    if not arts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(arts):
        return failure('Could not locate artifact ID', 404)

    artifact = arts[id_][1]

    r = None
    try:
        future = session.get(config.ipfs_uri + '/api/v0/object/stat', params={'arg': artifact})
        r = future.result()
        r.raise_for_status()
        j = r.json()
    except Exception:
        logger.exception('Received error stating files from IPFS, got response: %s',
                         r.content if r is not None else 'None')
        return failure('Could not locate IPFS resource', 400)

    # Convert stats to snake_case
    stats = {
        re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v
        for k, v in j.items()
    }
    stats['name'] = arts[id_][0]

    return success(stats)
