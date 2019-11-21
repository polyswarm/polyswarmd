import gevent

from geventwebsocket import WebSocketServer, WebSocketApplication, Resource

from .filter import (FilterManager)


class EventServer(WebSocketApplication):
    def __init__(self, *args):
        super().__init__(*args)
        self.filter_manager = FilterManager()

    def setup(self):
        self.filter_manager.setup_event_filters(self.chain)
        gevent.spawn(self.filter_poll)

    def filter_poll(self):
        with self.filter_manager.fetch() as results:
            for messages in results:
                if self.websockets is None:
                    return
                for msg in messages:
                    self.broadcast(msg)

    def broadcast(self, msg):
        for client in self.ws.handler.server.clients.values():
            client.ws.send(msg)


resource = Resource([('/events', EventServer)])

if __name__ == "__main__":
    server = WebSocketServer(('', 8000), resource, debug=True)
    server.serve_forever()
