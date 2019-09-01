from abc import ABC, abstractmethod


class AbstractArtifactServiceClient(ABC):
    """
    Abstract class that defines the interface all Artifact Service Clients must follow
    These functions are the features that polyswarmd requires in some artifact storage
    Namely, checking the status of the service, adding and retrieving artifacts, wrapping artifacts in some
    logical grouping (directory-like) and finding the details
    """
    def __init__(self, name, reachable_endpoint):
        self.name = name
        self.reachable_endpoint = reachable_endpoint

    @abstractmethod
    def add_artifacts(self, artifacts, session):
        """
        Add a list of artifacts to the service

        :param artifacts: list[tuple]: List of files to be added to the service.
        :param session: connection session
        :return: (int, json str): Tup[le of status code and json content returned by the server
        """
        raise NotImplementedError()


    @abstractmethod
    def add_artifact(self, artifact, session):
        """
        Add a list of artifacts to the service

        :param artifact: list[tuple]: List of files to be added to the service.
        :param session: connection session
        :return: (int, json str): Tup[le of status code and json content returned by the server
        """
        raise NotImplementedError()

    def check_uri(self, uri):
        """
        Check if the given uri is valid for the service.
        :param uri: uri to check
        :return: bool
        """
        raise NotImplementedError()

    @abstractmethod
    def details(self, identifier, index, session):
        """
        Get the details for a particular artifact with the given identifier.

        :param identifier: uri or other identifier for the artifact
        :param index: index of the artifact in a directory, or 0 if file is not a directory
        :param session: connection session
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def get_artifact(self, identifier, index, session):
        """
        Get the artifact at the given identifer and index

        :param identifier: uri or other identifier for the artifact
        :param index: index of the artifact in a directory, or 0 if file is not a directory
        :param session: connection session
        :return: (int, json str): Tup[le of status code and json content returned by the server
        """
        raise NotImplementedError()

    @abstractmethod
    def ls(self, identifier, session):
        """
        List the files in the directory at the given identifier

        :param identifier: uri or other identifier for the directory (or directory-like object)
        :param session: connection session
        :return: (int, json str): Tup[le of status code and json content returned by the server
        """
        raise NotImplementedError()

    @abstractmethod
    def status(self, session):
        """
        Performs an request against an artifact service to determine current running status

        :param session: connection session
        :return: (int, json str): Tup[le of status code and json content returned by the server
        """
        raise NotImplementedError()
