from typing import Any, Dict

from requests_futures.sessions import FuturesSession

from polyswarmd.config.service import Service
from polyswarmd.services.artifact.client import AbstractArtifactServiceClient


class ArtifactServices(Service):
    """Service for all ArtifactServices"""
    artifact_client: AbstractArtifactServiceClient

    def __init__(self, artifact_client: AbstractArtifactServiceClient, session: FuturesSession):
        self.artifact_client = artifact_client
        super().__init__('artifact_services', artifact_client.reachable_endpoint, session)

    def build_output(self, reachable) -> Dict[str, Any]:
        return {self.artifact_client.name.lower(): {'reachable': reachable,}}
