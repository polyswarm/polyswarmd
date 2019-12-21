from typing import List, Dict

from polyswarmd.config.service import Service


class Status:
    community: str
    services: List[Service]

    def __init__(self, community):
        self.community = community
        self.services = []

    def get_status(self):
        status = {'community': self.community}
        status.update(self.test_services())
        return status

    def register_services(self, services: List[Service]):
        for service in services:
            self.services.append(service)

    def register_service(self, service: Service):
        self.services.append(service)

    def test_services(self) -> Dict[str, bool]:
        return {service.name: service.get_service_state() for service in self.services}
