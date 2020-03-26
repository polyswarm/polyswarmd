from io import SEEK_END
import logging

from flask import Blueprint
from flask import current_app as app
from flask import g, request
from requests import HTTPError

from polyswarmd.services.artifact.exceptions import (
    ArtifactEmptyException,
    ArtifactException,
    ArtifactNotFoundException,
    ArtifactTooLargeException,
    InvalidUriException,
)
from polyswarmd.utils.response import failure, success

logger = logging.getLogger(__name__)
artifacts: Blueprint = Blueprint('artifacts', __name__)


def check_size(f, maxsize):
    """Return True if size is between 0 and the user's maximum

    >>> from collections import namedtuple
    >>> from io import StringIO
    >>> from werkzeug.datastructures import FileStorage
    >>> check_size(FileStorage(stream=StringIO('')), 1) #doctest:+ELLIPSIS
    Traceback (most recent call last):
    ...
    polyswarmd.services.artifact.exceptions.ArtifactEmptyException
    >>> check_size(namedtuple('TestFile', 'content_length')(32), 64)
    True
    >>> check_size(namedtuple('TestFile', 'content_length')(16), 11) #doctest:+ELLIPSIS
    Traceback (most recent call last):
    ...
    polyswarmd.services.artifact.exceptions.ArtifactTooLargeException
    """
    size = get_size(f)
    if maxsize < size:
        raise ArtifactTooLargeException()
    elif 0 >= size:
        raise ArtifactEmptyException()

    return True


def get_size(f):
    """Return ``f.content_length`` falling back to the position of ``f``'s stream end.

    >>> from io import StringIO
    >>> from werkzeug.datastructures import FileStorage
    >>> get_size(FileStorage(stream=StringIO('A' * 16)))
    16
    >>> from collections import namedtuple
    >>> get_size(namedtuple('TestFile', 'content_length')(32))
    32
    """
    if f.content_length:
        logger.debug('Content length %s', f.content_length)
        return f.content_length

    original_position = f.tell()
    f.seek(0, SEEK_END)
    size = f.tell()
    logger.debug('Seek length %s', size)
    f.seek(original_position)
    return size


@artifacts.route('/status', methods=['GET'])
@artifacts.route('/status/', methods=['GET'])
def get_artifacts_status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    try:
        return success(config.artifact.client.status(session))

    except HTTPError as e:
        return failure(e.response.content, e.response.status_code)
    except ArtifactException as e:
        return failure(e.message, 500)


@artifacts.route('', methods=['POST'])
@artifacts.route('/', methods=['POST'])
def post_artifacts():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        files = [(f'{i:06d}', f)
                 for (i, f) in enumerate(request.files.getlist(key='file'))
                 if check_size(f, g.user.max_artifact_size)]
    except (AttributeError, IOError):
        logger.error('Error checking file size')
        return failure('Unable to read file sizes', 400)
    except ArtifactTooLargeException:
        return failure('Artifact too large', 413)
    except ArtifactEmptyException:
        return failure('Artifact empty', 400)

    if not files:
        return failure('No artifacts', 400)
    if len(files) > config.artifact.limit:
        return failure('Too many artifacts', 400)

    try:
        response = success(config.artifact.client.add_artifacts(files, session))
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response


@artifacts.route('/<identifier>', methods=['GET'])
@artifacts.route('/<identifier>/', methods=['GET'])
def get_artifacts_identifier(identifier):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        arts = config.artifact.client.ls(identifier, session)
        if len(arts) > 256:
            return failure(f'Invalid {config.artifact.client.name} resource, too many links', 400)

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
@artifacts.route('/<identifier>/<int:id_>/', methods=['GET'])
def get_artifacts_identifier_id(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        response = config.artifact.client.get_artifact(
            identifier, session, index=id_, max_size=g.user.max_artifact_size
        )
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except InvalidUriException:
        response = failure('Invalid artifact URI', 400)
    except ArtifactNotFoundException:
        response = failure(f'Artifact with URI {identifier}/{id_} not found', 404)
    except ArtifactTooLargeException:
        response = failure(f'Artifact with URI {identifier}/{id_} too large', 400)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response


@artifacts.route('/<identifier>/<int:id_>/stat', methods=['GET'])
@artifacts.route('/<identifier>/<int:id_>/stat/', methods=['GET'])
def get_artifacts_identifier_id_stat(identifier, id_):
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']
    try:
        response = success(config.artifact.client.details(identifier, id_, session))
    except HTTPError as e:
        response = failure(e.response.content, e.response.status_code)
    except InvalidUriException:
        response = failure('Invalid artifact URI', 400)
    except ArtifactNotFoundException:
        response = failure(f'Artifact with URI {identifier} not found', 404)
    except ArtifactException as e:
        response = failure(e.message, 500)

    return response
