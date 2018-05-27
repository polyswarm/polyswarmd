import json
import re

import base58
import requests
from flask import Blueprint, request

from polyswarmd.config import ipfs_uri
from polyswarmd.response import success, failure

artifacts = Blueprint('artifacts', __name__)


def is_valid_ipfshash(ipfshash):
    # TODO: Further multihash validation
    try:
        return len(ipfshash) < 100 and base58.b58decode(ipfshash)
    except:
        pass

    return False


def list_artifacts(ipfshash):
    try:
        r = requests.get(
            ipfs_uri + '/api/v0/ls', params={'arg': ipfshash}, timeout=1)
        r.raise_for_status()
    except:
        return []

    links = [(l['Name'], l['Hash']) for l in r.json()['Objects'][0]['Links']]
    if not links:
        links = [('', r.json()['Objects'][0]['Hash'])]

    return links


@artifacts.route('', methods=['POST'])
def post_artifacts():
    files = [('file', (f.filename, f, 'application/octet-stream'))
             for f in request.files.getlist(key='file')]
    if len(files) > 256:
        return failure('Too many artifacts', 400)

    try:
        r = requests.post(
            ipfs_uri + '/api/v0/add',
            files=files,
            params={'wrap-with-directory': True})
        r.raise_for_status()
    except:
        return failure("Could not add artifacts to IPFS", 400)

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
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    arts = list_artifacts(ipfshash)
    if not arts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(arts):
        return failure('Could not locate artifact ID', 404)

    artifact = arts[id_][1]

    try:
        r = requests.get(
            ipfs_uri + '/api/v0/cat', params={'arg': artifact}, timeout=1)
        r.raise_for_status()
    except:
        return failure("Could not locate IPFS resource", 404)

    return r.content


@artifacts.route('/<ipfshash>/<int:id_>/stat', methods=['GET'])
def get_artifacts_ipfshash_id_stat(ipfshash, id_):
    if not is_valid_ipfshash(ipfshash):
        return failure('Invalid IPFS hash', 400)

    arts = list_artifacts(ipfshash)
    if not arts:
        return failure('Could not locate IPFS resource', 404)

    if id_ < 0 or id_ > 256 or id_ >= len(arts):
        return failure('Could not locate artifact ID', 404)

    artifact = arts[id_][1]

    try:
        r = requests.get(
            ipfs_uri + '/api/v0/object/stat', params={'arg': artifact})
        r.raise_for_status()
    except:
        return failure("Could not locate IPFS resource", 400)

    # Convert stats to snake_case
    stats = {
        re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v
        for k, v in r.json().items()
    }
    stats['name'] = arts[id_][0]

    return success(stats)
