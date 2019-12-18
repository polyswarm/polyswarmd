import gevent

from abc import ABC, abstractmethod
from typing import Any, Dict

from requests import HTTPError

DEFAULT_FAILED_STATE: Dict[str, Any] = {'reachable': False}
DEFAULT_SUCCESS_STATE: Dict[str, Any] = {'reachable': True}


class Service(ABC):
    """Service that polyswarmd connects to """
    name: str

    def __init__(self, name):
        self.name = name

    def wait_until_live(self):
        while True:
            try:
                return self.test_reachable()
            except HTTPError:
                gevent.sleep(1)
                continue

    def get_service_state(self) -> Dict[str, Any]:
        try:
            self.test_reachable()
            return DEFAULT_SUCCESS_STATE
        except HTTPError:
            return DEFAULT_FAILED_STATE

    @abstractmethod
    def test_reachable(self):
        """
        Test if service can be reached

        raises HTTPError when not live
        """
        raise NotImplementedError()
