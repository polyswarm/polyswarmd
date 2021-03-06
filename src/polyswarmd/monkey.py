"""
   isort:skip_file
"""
from concurrent.futures import ThreadPoolExecutor

import web3
from gevent import monkey
from requests_futures.sessions import FuturesSession

session = FuturesSession(
    executor=ThreadPoolExecutor(), adapter_kwargs={
        'max_retries': 5,
        'pool_maxsize': 100
    }
)


def patch_all():
    patch_gevent()
    patch_web3()


def patch_gevent():
    monkey.patch_all()


def patch_web3():

    def make_post_request(endpoint_uri, data, *args, **kwargs):
        kwargs.setdefault('timeout', 1)
        future = session.post(endpoint_uri, data=data, *args, **kwargs)
        response = future.result()
        response.raise_for_status()

        return response.content

    web3.providers.rpc.make_post_request = make_post_request
