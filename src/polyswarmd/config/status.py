from typing import Dict, List, Union

from polyswarmd.config.service import Service


class Status:
    community: str
    services: List[Service]

    def __init__(self, community):
        self.community = community
        self.services = []

    def get_status(self):
        status: Dict = {'community': self.community}
        for k, v in self.test_services().items():
            status[k] = v
        return status

    def register_services(self, services: List[Service]):
        for service in services:
            self.services.append(service)

    def register_service(self, service: Service):
        self.services.append(service)

    def test_services(self) -> Dict[str, Union[str, bool, Dict]]:
        # The return type may NOT be correct. It was produced by referencing the original
        # implementation. If it's the case that `test_services` (and it's subclass's impl)
        # *only* returns `bool` now, just drop this to `Dict[str, bool]` or whatever.
        return {service.name: service.get_service_state() for service in self.services}
