from polyswarmd.exceptions import PolyswarmdException


class ArtifactException(PolyswarmdException):
    pass


class InvalidUriException(ArtifactException):
    pass


class ArtifactNotFoundException(ArtifactException):
    pass


class ArtifactEmptyException(ArtifactException):
    pass


class ArtifactTooLargeException(ArtifactException):
    pass
