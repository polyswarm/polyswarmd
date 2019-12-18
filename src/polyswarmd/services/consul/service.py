import logging

from requests_futures.sessions import FuturesSession

from polyswarmd.services.service import Service

logger = logging.getLogger(__name__)


class ConsulService(Service):
    """Service for Consul"""

    def __init__(self, uri: str, session: FuturesSession):
        super().__init__('consul', uri, session)
