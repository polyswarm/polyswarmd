import web3
from gevent import monkey
from requests_futures.sessions import FuturesSession
from requests.exceptions import ConnectionError
MAX_RETRIES = 2

session = FuturesSession()


def patch_all():
    patch_gevent()
    patch_web3()


def patch_gevent():
    monkey.patch_all()


def patch_web3():
    def make_post_request(endpoint_uri, data, *args, **kwargs):
        global session
        kwargs.setdefault('timeout', 1)
        tries = 0
        while tries < MAX_RETRIES:
                future = session.post(endpoint_uri, data=data, *args, **kwargs)
            try:
                response = future.result()
            except ConnectionError as e:
                tries += 1
                logger.error('Connection error: %s', e)
                # Create new session since the last closed
                session = FuturesSession()
                continue
            response.raise_for_status()
            return response.content
        logger.error('unable able to recreate session')

    web3.providers.rpc.make_post_request = make_post_request
