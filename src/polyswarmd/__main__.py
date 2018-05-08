from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from polyswarmd import app

def main():
    server = pywsgi.WSGIServer(
        ('', 31337), app, handler_class=WebSocketHandler)
    server.serve_forever()

if __name__ == '__main__':
    main()
