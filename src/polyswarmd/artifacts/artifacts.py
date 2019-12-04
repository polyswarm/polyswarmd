import logging

from flask import Blueprint
from flask import current_app as app
from flask import g, request
from requests import HTTPError

from polyswarmd.artifacts.exceptions import (
    ArtifactException,
    ArtifactNotFoundException,
    ArtifactSizeException,
    InvalidUriException,
)
from polyswarmd.response import failure, success

logger = logging.getLogger(__name__)
artifacts = Blueprint('artifacts', __name__)


@artifacts.route('/status', methods=['GET'])
def get_artifacts_status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    try:
        return success(config.artifact_client.status(session))

    except HTTPError as e:
        return failure(e.response.content, e.response.status_code)
    except ArtifactException as e:
        return failure(e.message, 500)


@artifacts.route('', methods=['POST'])
def post_artifacts():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    # Since we aren't using MAX_CONTENT_LENGTH anymore, we have to check each.
    files = [(f'{i:06d}', f)
             for (i, f) in enumerate(request.files.getlist(key='file'))
             if 0 < f.content_length <= g.user.max_artifact_size]
    if len(files) < len(request.files.getlist(key='file')):
        return failure(f'Some artifact length is not between 0 bytes and max size of {g.user.max_artifact_size}', 413)

    if not files:
        return failure('No artifacts', 400)
    if len(files) > config.artifact_limit:
        return failure('Too many artifacts', 400)

    try:
        response = success(config.artifact_client.add_artifacts(files, session))
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response


@artifacts.route('/<identifier>', methods=['GET'])
def get_artifacts_identifier(identifier):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        arts = config.artifact_client.ls(identifier, session)
        if len(arts) > 256:
            return failure(f'Invalid {config.artifact_client.name} resource, too many links', 400)

        response = success([{'name': a[0], 'hash': a[1]} for a in arts])

    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except InvalidUriException:
        response = failure('Invalid artifact URI', 400)
    except ArtifactNotFoundException:
        response = failure(f'Artifact with URI {identifier} not found', 404)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response


@artifacts.route('/<identifier>/<int:id_>', methods=['GET'])
def get_artifacts_identifier_id(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        response = config.artifact_client.get_artifact(
            identifier, session, index=id_, max_size=g.user.max_artifact_size
        )
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except InvalidUriException:
        response = failure('Invalid artifact URI', 400)
    except ArtifactNotFoundException:
        response = failure(f'Artifact with URI {identifier}/{id_} not found', 404)
    except ArtifactSizeException:
        response = failure(f'Artifact with URI {identifier}/{id_} too large', 400)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response


@artifacts.route('/<identifier>/<int:id_>/stat', methods=['GET'])
def get_artifacts_identifier_id_stat(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        response = success(config.artifact_client.details(identifier, id_, session))
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except InvalidUriException:
        response = failure('Invalid artifact URI', 400)
    except ArtifactNotFoundException:
        response = failure(f'Artifact with URI {identifier} not found', 404)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response
