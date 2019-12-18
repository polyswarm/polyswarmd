from requests import HTTPError
from requests_futures.sessions import FuturesSession
from typing import Any, Dict

from polyswarmd.services.artifact.client import AbstractArtifactServiceClient
from polyswarmd.services.service import Service


class ArtifactServices(Service):
    """Service declaration for all ArtifactServices"""
    artifact_client: AbstractArtifactServiceClient
    session: FuturesSession

    def __init__(self, artifact_client: AbstractArtifactServiceClient, session: FuturesSession):
        super().__init__('artifact_services')
        self.artifact_client = artifact_client
        self.session = session

    def test_reachable(self):
        future = self.session.post(self.artifact_client.reachable_endpoint)
        response = future.result()
        response.raise_for_status()

    def build_output(self, reachable) -> Dict[str, Any]:
        return {
            self.artifact_client.name.lower(): {
                'reachable': reachable,
            }
        }

    def get_service_state(self) -> Dict[str, Any]:
        try:
            self.test_reachable()
            return self.build_output(reachable=True)
        except HTTPError:
            return self.build_output(reachable=True)
