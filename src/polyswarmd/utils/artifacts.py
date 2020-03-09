import logging
from io import SEEK_END

from polyswarmd.services.artifact.exceptions import ArtifactTooLargeException, ArtifactEmptyException

logger = logging.getLogger(__name__)


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
