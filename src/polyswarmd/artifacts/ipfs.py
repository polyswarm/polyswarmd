import base58
import ipfshttpclient
import logging
import re
import uuid

import urllib3

from polyswarmd.artifacts.client import AbstractArtifactServiceClient
from polyswarmd.artifacts.exceptions import ArtifactSizeException, InvalidUriException, \
    ArtifactNotFoundException

logger = logging.getLogger(__name__)


class IpfsServiceClient(AbstractArtifactServiceClient):
    """
    Artifact Service Client for IPFS.

    Uses MFS for adding to directories, since limits on IPFS API requests prevent 256 file requests.
    """
    def __init__(self, base_uri):
        self.base_uri = base_uri
        reachable_endpoint = f"{self.base_uri}{'/api/v0/bootstrap'}"
        url = urllib3.util.parse_url(self.base_uri)
        client_connect_url = f'/dns/{url.host}/tcp/{url.port}/{url.scheme}'
        self.client = ipfshttpclient.connect(client_connect_url, session=True)
        super().__init__('IPFS', reachable_endpoint)

    @staticmethod
    def check_ls(artifacts, index, max_size=None):
        if index < 0 or index > 256 or index >= len(artifacts):
            raise ArtifactNotFoundException('Could not locate artifact ID')

        _, artifact, size = artifacts[index]
        if max_size and size > max_size:
            raise ArtifactSizeException('Artifact size greater than maximum allowed')

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
        ipfs_uri = self.client.add_str(artifact)
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

        stat = self.client.object.stat(artifact, session)
        logger.info(f'Got artifact details {stat}')

        # Convert stats to snake_case
        stats = {
            re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v
            for k, v in stat.items()
        }
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

        return self.client.cat(uri)

    def ls(self, uri, session):
        self.check_uri(uri)
        stats = self.client.object.stat(uri)
        ls = self.client.object.links(uri)

        # Return self if not directory
        if stats.get('NumLinks', 0) == 0:
            return [('', stats.get('Hash', ''), stats.get('DataSize'))]

        if ls:
            links = [(l.get('Name', ''), l.get('Hash', ''), l.get('Size', 0)) for l in ls.get('Links', [])]

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
                if self.client.files.ls(directory_name):
                    logger.critical('Got collision on names. Some assumptions were wrong')
                    continue
            except ipfshttpclient.exceptions.ErrorResponse:
                # Raises error if it doesn't exists, so we want to continue in this case.
                self.client.files.mkdir(directory_name)
                return directory_name
