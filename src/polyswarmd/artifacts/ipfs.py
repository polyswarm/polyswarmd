import base58
import functools
import json
import logging
import re
import uuid

from requests import HTTPError

from polyswarmd.artifacts.client import AbstractArtifactServiceClient
from polyswarmd.artifacts.exceptions import ArtifactException, ArtifactSizeException, InvalidUriException, \
    ArtifactNotFoundException

logger = logging.getLogger(__name__)


def catch_ipfs_errors(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (HTTPError, ArtifactException) as e:
            raise e
        except Exception:
            logger.exception('Received error from IPFS')
            raise ArtifactException(f'Error executing IPFS command {func.__name__}')

    return wrapper


class IpfsServiceClient(AbstractArtifactServiceClient):
    """
    Artifact Service Client for IPFS.

    Uses MFS for adding to directories, since limits on IPFS API requests prevent 256 file requests.
    """
    def __init__(self, base_uri):
        self.base_uri = base_uri
        reachable_endpoint = f"{self.base_uri}{'/api/v0/bootstrap'}"
        super().__init__('IPFS', reachable_endpoint)

    @staticmethod
    def check_ls(artifacts, index, max_size=None):
        if not artifacts:
            raise ArtifactNotFoundException('Could not locate IPFS resource')

        if index < 0 or index > 256 or index >= len(artifacts):
            raise ArtifactNotFoundException('Could not locate artifact ID')

        _, artifact, size = artifacts[index]
        if max_size and size > max_size:
            raise ArtifactSizeException('Artifact size greater than maximum allowed')

        return artifacts[index]

    @staticmethod
    def check_redis(uri, redis):
        try:
            result = redis.get(f'polyswarmd:{uri}')
            if result:
                return result
        except RuntimeError:
            # happens if redis is not configured and websocket poll calls this
            pass

    def add_artifacts(self, artifacts, session):
        directory = self._mfs_mkdir(session)
        for artifact in artifacts:
            ipfs_uri = self._add(artifact, session)
            filename = artifact[1][0]
            self._mfs_copy(directory, filename, ipfs_uri, session)

        stat = self._mfs_stat(directory, session)
        return stat.get('Hash', '')

    def add_artifact(self, artifact, session, redis=None):
        ipfs_uri = self._add(artifact, session)
        if redis:
            redis.set(f'polyswarmd:{ipfs_uri}', artifact[1][1], ex=300)

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

        stat = self._stat(artifact, session)

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

        return self._cat(uri, session)

    def ls(self, uri, session):
        self.check_uri(uri)
        stats = self._stat(uri, session)
        ls = self._ls(uri, session)

        if stats.get('NumLinks', 0) == 0:
            return [('', stats.get('Hash', ''), stats.get('DataSize'))]

        objects = ls.get('Objects', [])
        if objects:
            links = [(l.get('Name', ''), l.get('Hash', ''), l.get('Size', 0)) for l in objects[0].get('Links', [])]

            if not links:
                links = [('', stats.get('Hash', ''), stats.get('DataSize', 0))]

            return links

        return []

    def status(self, session):
        return {'online': self._sys(session)}

    @catch_ipfs_errors
    def _add(self, file, session):
        future = session.post(
            self.base_uri + '/api/v0/add',
            files=[file])
        r = future.result()
        r.raise_for_status()
        return json.loads(r.text.splitlines()[-1])['Hash']

    @catch_ipfs_errors
    def _cat(self, ipfs_uri, session):
        self.check_uri(ipfs_uri)
        future = session.get(self.base_uri + '/api/v0/cat', params={'arg': ipfs_uri}, timeout=1)
        r = future.result()
        r.raise_for_status()
        return r.content

    @catch_ipfs_errors
    def _ls(self, ipfs_uri, session):
        future = session.get(self.base_uri + '/api/v0/ls', params={'arg': ipfs_uri}, timeout=1)
        r = future.result()
        r.raise_for_status()
        return r.json()

    @catch_ipfs_errors
    def _mfs_copy(self, directory, filename, ipfs_uri, session):
        self.check_uri(ipfs_uri)
        artifacts = self._mfs_ls(directory, session)

        if artifacts is not None and any((artifact for artifact in artifacts if artifact.get('Hash', '') == ipfs_uri)):
            logger.warning('Attempted to copy %s: %s into %s, but it already exists', filename, ipfs_uri, directory)
            # Return successfully since it is in the given directory
            return

        future = session.get(self.base_uri + '/api/v0/files/cp', params={
            'arg': [
                f'/ipfs/{ipfs_uri}',
                f'{directory}/{filename}'
            ]
        }, timeout=1)
        r = future.result()
        r.raise_for_status()

        return

    @catch_ipfs_errors
    def _mfs_mkdir(self, session):
        while True:
            directory_name = f'/{str(uuid.uuid4())}'
            # Try again if name is taken (Should never happen)
            try:
                if self._mfs_ls(directory_name, session)[1]:
                    logger.critical('Got collision on names. Some assumptions were wrong')
                    continue
            except HTTPError:
                # Raises error if it doesn't exists, so we want to continue in this case.
                pass

            future = session.get(self.base_uri + '/api/v0/files/mkdir', params={
                'arg': directory_name,
                'parents': True,
            }, timeout=1)
            r = future.result()
            r.raise_for_status()

            return directory_name

    def _mfs_ls(self, directory, session):
        future = session.get(self.base_uri + '/api/v0/files/ls', params={
            'arg': directory,
            'l': True
        }, timeout=1)
        r = future.result()
        r.raise_for_status()

        return r.json().get('Entries', [])

    @catch_ipfs_errors
    def _mfs_stat(self, directory, session):
        future = session.get(self.base_uri + '/api/v0/files/stat', params={
            'arg': directory,
        }, timeout=1)
        r = future.result()
        r.raise_for_status()

        return r.json()

    @catch_ipfs_errors
    def _stat(self, ipfs_uri, session):
        future = session.get(self.base_uri + '/api/v0/object/stat', params={'arg': ipfs_uri})
        r = future.result()
        r.raise_for_status()
        return r.json()

    @catch_ipfs_errors
    def _sys(self, session):
        future = session.get(self.base_uri + '/api/v0/diag/sys', timeout=1)
        r = future.result()
        r.raise_for_status()
        return r.json()['net']['online']
