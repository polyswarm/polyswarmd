import logging

from requests_futures.sessions import FuturesSession

from polyswarmd.services.service import Service

logger = logging.getLogger(__name__)


class ConsulService(Service):
    """Service declaration for Consul"""
    session: FuturesSession
    uri: str

    def __init__(self, uri: str, session: FuturesSession):
        super().__init__('consul')
        self.uri = uri
        self.session = session

    def test_reachable(self):
        future = self.session.post(self.uri)
        response = future.result()
        response.raise_for_status()
