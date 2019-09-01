import json
import logging
import os
import re

import base58
import requests
import uuid

from flask import g

from polyswarmd.artifacts.client import AbstractArtifactServiceClient


logger = logging.getLogger(__name__)


class IpfsServiceClient(AbstractArtifactServiceClient):
    """
    Artifact Service Client for IPFS.

    Uses MFS for adding to directories, since limits on IPFS API requests prevent 256 file requests.
    """

    def __init__(self, base_uri):
        self.base_uri = base_uri
        reachable_endpoint = "{}{}".format(self.base_uri, '/api/v0/bootstrap')
        super().__init__('IPFS', reachable_endpoint)

    def add_artifacts(self, artifacts, session):
        status, directory = self.mfs_mkdir(session)
        if status // 100 != 2:
            return status, None

        for artifact in artifacts:
            status, ipfs_uri = self.add(artifact, session)
            filename = artifact[1][0]
            self.mfs_copy(directory, filename, ipfs_uri, session)

        status, stat = self.mfs_stat(directory, session)
        if status // 100 == 2:
            return status, stat.get('Hash', '')
        else:
            return status, None

    def add_artifact(self, artifact, session):
        return self.add(artifact, session)

    # noinspection PyBroadException
    def check_uri(self, uri):
        # TODO: Further multihash validation
        try:
            return len(uri) < 100 and base58.b58decode(uri)
        except Exception:
            return False

    # noinspection PyBroadException
    def details(self, uri, index, session):
        if not self.check_uri(uri):
            return 400, 'Invalid IPFS hash'

        arts = self.ls(uri, session)
        if not arts:
            return 404, 'Could not locate IPFS resource'

        if index < 0 or index > 256 or index >= len(arts):
            return 404, 'Could not locate artifact ID'

        artifact = arts[index][1]

        r = None
        try:
            future = session.get(self.base_uri + '/api/v0/object/stat', params={'arg': artifact})
            r = future.result()
            r.raise_for_status()
            j = r.json()
        except Exception:
            logger.exception('Received error stating files from IPFS, got response: %s',
                             r.content if r is not None else 'None')
            return 400, 'Could not locate IPFS resource'

        # Convert stats to snake_case
        stats = {
            re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', k).lower(): v
            for k, v in j.items()
        }
        stats['name'] = arts[index][0]

        return 200, stats

    def get_artifact(self, uri, session, index=None, max_size=None):
        if not self.check_uri(uri):
            return 400, 'Invalid IPFS hash'

        if index is not None:
            artifacts = self.ls(uri, session)
            if not artifacts:
                return 404, 'Could not locate IPFS resource'

            if index < 0 or index > 256 or index >= len(artifacts):
                return 404, 'Could not locate artifact ID'

            _, artifact, size = artifacts[index]
            if max_size and size > max_size:
                return 400, 'Artifact size greater than maximum allowed'

            uri = artifact

        return self.cat(uri, session)

    # noinspection PyBroadException
    def ls(self, uri, session):
        if not self.check_uri(uri):
            return 400, 'Invalid IPFS hash'

        r = None
        try:
            stat_future = session.get(self.base_uri + '/api/v0/object/stat', params={'arg': uri})
            ls_future = session.get(self.base_uri + '/api/v0/ls', params={'arg': uri}, timeout=1)

            r = stat_future.result()
            r.raise_for_status()
            stats = r.json()

            r = ls_future.result()
            r.raise_for_status()
            ls = r.json()
        except Exception:
            logger.exception('Received error listing files from IPFS, got response: %s',
                             r.content if r is not None else 'None')
            return []

        if stats.get('NumLinks', 0) == 0:
            return [('', stats.get('Hash', ''), stats.get('DataSize'))]

        objects = ls.get('Objects', [])
        if objects:
            links = [(l.get('Name', ''), l.get('Hash', ''), l.get('Size', 0)) for l in objects[0].get('Links', [])]

            if not links:
                links = [('', stats.get('Hash', ''), stats.get('DataSize', 0))]

            return links

        return []

    # noinspection PyBroadException
    def status(self, session):
        r = None
        try:
            future = session.get(self.base_uri + '/api/v0/diag/sys', timeout=1)
            r = future.result()
            r.raise_for_status()
        except Exception:
            logger.exception('Received error connecting to IPFS, got response: %s',
                             r.content if r is not None else 'None')
            return 500, 'Could not connect to IPFS'

        online = r.json()['net']['online']
        return 200, {'online': online}

    def add(self, file, session):
        try:
            future = session.post(
                self.base_uri + '/api/v0/add',
                files=[file])
            r = future.result()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.exception('ADD FAIL')
            return e.response.status_code, None

        return 201, json.loads(r.text.splitlines()[-1])['Hash']

    def cat(self, ipfs_uri, session):
        if not self.check_uri(ipfs_uri):
            return 400, 'Invalid IPFS hash'

        try:
            future = session.get(self.base_uri + '/api/v0/cat', params={'arg': ipfs_uri}, timeout=1)
            r = future.result()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.exception('CAT FAIL')
            return e.response.status_code, None

        return 200, r.content

    def mfs_copy(self, directory, filename, ipfs_uri, session):
        if not self.check_uri(ipfs_uri):
            return 400, 'Invalid IPFS hash'

        status, artifacts = self.mfs_ls(directory, session)
        if status // 100 != 2:
            return 400

        if artifacts is not None and any((artifact for artifact in artifacts if artifact.get('Hash', '') == ipfs_uri)):
            logger.warning('Attempted to copy %s: %s into %s, but it already exists', filename, ipfs_uri, directory)
            # Return successfully since it is in the given directory
            return 200

        try:
            future = session.get(self.base_uri + '/api/v0/files/cp', params={
                'arg': [
                    '/ipfs/{0}'.format(ipfs_uri),
                    '/{0}/{1}'.format(directory, filename)
                ]
            }, timeout=1)
            r = future.result()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.exception('COPY FAIL')
            return e.response.status_code

        return 200

    def mfs_mkdir(self, session):
        while True:
            directory_name = uuid.uuid4()
            # Try again if name is taken (Should never happen)
            if self.mfs_ls(directory_name, session)[1]:
                logger.critical('Got collision on names. Some assumptions were wrong')
                continue

            try:
                future = session.get(self.base_uri + '/api/v0/files/mkdir', params={
                    'arg': '/{0}'.format(directory_name),
                    'parents': True,
                }, timeout=1)
                r = future.result()
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                return e.response.status_code, None

            return 200, str(directory_name)

    def mfs_ls(self, directory, session):
        try:
            future = session.get(self.base_uri + '/api/v0/files/ls', params={
                'arg': '/{0}'.format(directory),
                'l': True
            }, timeout=1)
            r = future.result()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return e.response.status_code, None

        return 200, r.json().get('Entries', [])

    def mfs_stat(self, directory, session):
        try:
            future = session.get(self.base_uri + '/api/v0/files/stat', params={
                'arg': '/{0}'.format(directory),
            }, timeout=1)
            r = future.result()
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return e.response.status_code, None

        return 200, r.json()
