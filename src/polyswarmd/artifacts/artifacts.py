import logging

from flask import current_app as app, g, Blueprint, request

from polyswarmd.response import success, failure

logger = logging.getLogger(__name__)
artifacts = Blueprint('artifacts', __name__)

# 100MB limit
# TODO: Should this be configurable in config file?
MAX_ARTIFACT_SIZE_REGULAR = 32 * 1024 * 1024
MAX_ARTIFACT_SIZE_ANONYMOUS = 2 * 1024 * 1024


@artifacts.route('/status', methods=['GET'])
def get_artifacts_status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    status, response = config.artifact_client.status(session)
    if status // 100 != 2:
        return failure(response, status)

    return success(response)


@artifacts.route('', methods=['POST'])
def post_artifacts():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    files = [('file', (f.filename, f, 'application/octet-stream')) for f in request.files.getlist(key='file')]
    if not files:
        return failure('No artifacts', 400)
    if len(files) > config.artifact_limit:
        return failure('Too many artifacts', 400)

    status_code, identifier = config.artifact_client.add_artifacts(files, session)
    if status_code // 100 != 2:
        return failure('Could not add artifacts to IPFS', status_code)
    else:
        return success(identifier)


@artifacts.route('/<identifier>', methods=['GET'])
def get_artifacts_identifier(identifier):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    arts = config.artifact_client.ls(identifier, session)
    if not arts:
        return failure('Could not locate {0} resource'.format(config.artifact_client.name), 404)
    if len(arts) > 256:
        return failure('Invalid {0} resource, too many links'.format(config.artifact_client.name), 400)

    return success([{'name': a[0], 'hash': a[1]} for a in arts])


@artifacts.route('/<identifier>/<int:id_>', methods=['GET'])
def get_artifacts_identifier_id(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    status, response = config.artifact_client.get_artifact(identifier,
                                                           session,
                                                           index=id_,
                                                           max_size=g.user.max_artifact_size)
    if status // 100 != 2:
        return failure(response, status)

    return response


@artifacts.route('/<identifier>/<int:id_>/stat', methods=['GET'])
def get_artifacts_identifier_id_stat(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    status, response = config.artifact_client.details(identifier, id_, session)
    if status // 100 != 2:
        return failure(response, status)

    return success(response)
