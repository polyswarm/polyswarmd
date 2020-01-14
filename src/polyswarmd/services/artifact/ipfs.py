import logging
import os
import re
import uuid

import base58
import ipfshttpclient
from urllib3.util import parse_url

from polyswarmd.services.artifact.client import AbstractArtifactServiceClient
from polyswarmd.services.artifact.exceptions import (
    ArtifactException,
    ArtifactNotFoundException,
    ArtifactTooLargeException,
    InvalidUriException,
)

logger = logging.getLogger(__name__)


class IpfsServiceClient(AbstractArtifactServiceClient):
    """
    Artifact Service Client for IPFS.

    Uses MFS for adding to directories, since limits on IPFS API requests prevent 256 file requests.
    """

    def __init__(self, base_uri=None):
        self.base_uri = base_uri or os.environ.get('IPFS_URI')
        reachable_endpoint = f"{self.base_uri}{'/api/v0/bootstrap'}"
        super().__init__('IPFS', reachable_endpoint)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            url = parse_url(self.base_uri)
            self._client = ipfshttpclient.connect(
                f'/dns/{url.host}/tcp/{url.port}/{url.scheme}', session=True
            )

        return self.client

    @staticmethod
    def check_ls(artifacts, index, max_size=None):
        if index < 0 or index > 256 or index >= len(artifacts):
            raise ArtifactNotFoundException('Could not locate artifact ID')

        _, artifact, size = artifacts[index]
        if max_size and size > max_size:
            raise ArtifactTooLargeException()

        return artifacts[index]

    @staticmethod
    def check_redis(uri, redis):
        if not redis:
            return None

        try:
            result = redis.get(f'polyswarmd:{uri}')
            if result:
                return result
        except RuntimeError:
            # happens if redis is not configured and websocket poll calls this
            pass

    def add_artifacts(self, artifacts, session):
        directory = self.mkdir()
        for artifact in artifacts:
            response = self.client.add(artifact[1], pin=False)
            filename = artifact[0]
            source = f'/ipfs/{response["Hash"]}'
            dest = f'{directory}/{filename}'
            self.client.files.cp(source, dest)

        stat = self.client.files.stat(directory)
        return stat.get('Hash', '')

    def add_artifact(self, artifact, session, redis=None):
        # We cannot add a string using client.add, it will take a string or b-string and tries to load a file
        ipfs_uri = self.client.add_str(artifact)
        # add_str does not accept any way to set pin=False, so we have to remove in a second call
        try:
            self.client.pin.rm(ipfs_uri, timeout=1)
        except (
            ipfshttpclient.exceptions.ErrorResponse, ipfshttpclient.exceptions.TimeoutError
        ) as e:
            logger.warning('Got error when removing pin: %s', e)
            # Only seen when the pin didn't exist, not a big deal
            pass

        if redis:
            redis.set(f'polyswarmd:{ipfs_uri}', artifact, ex=300)

        return ipfs_uri

    # noinspection PyBroadException
    def check_uri(self, uri):
        # TODO: Further multihash validation
        try:
            return len(uri) < 100 and base58.b58decode(uri)
        except Exception:
            raise InvalidUriException()

    def details(self, uri, index, session):
        self.check_uri(uri)
        artifacts = self.ls(uri, session)
        name, artifact, _ = IpfsServiceClient.check_ls(artifacts, index)

        try:
            stat = self.client.object.stat(artifact, session, timeout=1)
        except ipfshttpclient.exceptions.TimeoutError:
            raise ArtifactNotFoundException('Could not locate artifact ID')

        logger.info(f'Got artifact details {stat}')

        # Convert stats to snake_case
        stats = {re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v for k, v in stat.items()}
        stats['name'] = name

        return stats

    def get_artifact(self, uri, session, index=None, max_size=None, redis=None):
        self.check_uri(uri)
        redis_response = IpfsServiceClient.check_redis(uri, redis)
        if redis_response:
            return redis_response

        if index is not None:
            artifacts = self.ls(uri, session)
            _, uri, _ = IpfsServiceClient.check_ls(artifacts, index, max_size)

        try:
            return self.client.cat(uri, timeout=1)
        except ipfshttpclient.exceptions.TimeoutError:
            raise ArtifactNotFoundException('Could not locate artifact ID')

    def ls(self, uri, session):
        self.check_uri(uri)
        try:
            stats = self.client.object.stat(uri, timeout=1)
            ls = self.client.object.links(uri, timeout=1)
        except ipfshttpclient.exceptions.TimeoutError:
            raise ArtifactException('Timeout running ls')

        # Return self if not directory
        if stats.get('NumLinks', 0) == 0:
            return [('', stats.get('Hash', ''), stats.get('DataSize'))]

        if ls:
            links = [(l.get('Name', ''), l.get('Hash', ''), l.get('Size', 0))
                     for l in ls.get('Links', [])]

            if not links:
                links = [('', stats.get('Hash', ''), stats.get('DataSize', 0))]

            return links

        raise ArtifactNotFoundException('Could not locate IPFS resource')

    def status(self, session):
        return {'online': self.client.object.sys()['net']['online']}

    def mkdir(self):
        while True:
            directory_name = f'/{str(uuid.uuid4())}'
            # Try again if name is taken (Should never happen)
            try:
                if self.client.files.ls(directory_name, timeout=1):
                    logger.critical('Got collision on names. Some assumptions were wrong')
                    continue
            except (ipfshttpclient.exceptions.ErrorResponse, ipfshttpclient.exceptions.TimeoutError):
                # Raises error if it doesn't exists, so we want to continue in this case.
                break

        try:
            self.client.files.mkdir(directory_name, timeout=1)
            return directory_name
        except ipfshttpclient.exceptions.TimeoutError:
            raise ArtifactException('Timeout running ls')
