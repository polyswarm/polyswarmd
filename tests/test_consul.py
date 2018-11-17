import io

import requests_mock


def test_post_artifacts():
    global consul_url
    consul_url = "http://localhost:1600/v1/kv/gamma/"

    from polyswarmd import config
    config.consul_url = consul_url
    pass

if __name__ == "__main__":
    test_post_artifacts(None)