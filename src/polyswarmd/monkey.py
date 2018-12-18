# Monkey patch for gevent compat
def patch_all():
    from gevent import monkey
    monkey.patch_all()

    from psycogreen.gevent import patch_psycopg
    patch_psycopg()

    import requests
    import web3.utils

    # When using gevent web3 is exhausting connection pool, think due to unnecessary session caching layer over requests
    def patched_make_post_request(endpoint_uri, data, *args, **kwargs):
        kwargs.setdefault('timeout', 10)
        response = requests.post(endpoint_uri, data=data, *args, **kwargs)
        response.raise_for_status()

        return response.content

    web3.utils.make_post_request = patched_make_post_request
