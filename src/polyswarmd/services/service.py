import gevent

from abc import ABC, abstractmethod
from typing import Any, Dict

from requests import HTTPError
from requests_futures.sessions import FuturesSession


class Service:
    """Service that polyswarmd connects to """
    session: FuturesSession
    name: str
    uri: str

    def __init__(self, name, uri, session):
        self.name = name
        self.uri = uri
        self.session = session

    def wait_until_live(self):
        while not self.test_reachable():
            gevent.sleep(1)

    def test_reachable(self) -> bool:
        try:
            self.connect_to_service()
            return True
        except HTTPError:
            return False

    def connect_to_service(self):
        future = self.session.post(self.uri)
        response = future.result()
        response.raise_for_status()

    def get_service_state(self) -> Dict[str, Any]:
        return self.build_output(self.test_reachable())

    def build_output(self, reachable) -> Dict[str, Any]:
        return {'reachable': reachable}
