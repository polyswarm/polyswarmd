"""
   isort:skip_file
"""
import os
from concurrent.futures import ThreadPoolExecutor
from requests_futures.sessions import FuturesSession
from polyswarmd.monkey import patch_all

patch_all()

import datetime

import functools
import logging

from flask import Flask, g, request
from flask_caching import Cache

from polyswarmd.config import Config, is_service_reachable, DEFAULT_FALLBACK_SIZE

from polyswarmd.logger import init_logging  # noqa

from polyswarmd.profiler import setup_profiler
from polyswarmd.response import success, failure, install_error_handlers

logger = logging.getLogger(__name__)
cache: Cache = Cache(config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 30})

# Set up our app object
app = Flask(__name__)
_config = Config.auto()
app.config['POLYSWARMD'] = _config
# Setting this value works even when Content-Length is omitted, we must have it
app.config['MAX_ARTIFACT_SIZE'] = _config.max_artifact_size * _config.artifact_limit

session = FuturesSession(executor=ThreadPoolExecutor(4), adapter_kwargs={'max_retries': 2})

session.request = functools.partial(session.request, timeout=10)

app.config['REQUESTS_SESSION'] = session
app.config['CHECK_BLOCK_LIMIT'] = True
app.config['THREADPOOL'] = ThreadPoolExecutor()

install_error_handlers(app)

from polyswarmd.eth import misc
from polyswarmd.artifacts.artifacts import artifacts
from polyswarmd.balances import balances
from polyswarmd.bounties import bounties
from polyswarmd.relay import relay
from polyswarmd.offers import offers
from polyswarmd.staking import staking
from polyswarmd.event_message import init_websockets

app.register_blueprint(misc, url_prefix='/')
app.register_blueprint(artifacts, url_prefix='/artifacts')
app.register_blueprint(balances, url_prefix='/balances')
app.register_blueprint(bounties, url_prefix='/bounties')
app.register_blueprint(relay, url_prefix='/relay')
app.register_blueprint(offers, url_prefix='/offers')
app.register_blueprint(staking, url_prefix='/staking')

if not os.getenv('DISABLE_WEBSOCKETS', False):
    init_websockets(app)

setup_profiler(app)
cache.init_app(app)

AUTH_WHITELIST = {'/status', '/relay/withdrawal', '/transactions'}


@cache.memoize(30)
def get_auth(api_key, auth_uri):
    future = session.get(auth_uri, headers={'Authorization': api_key})
    return future.result()


@cache.memoize(30)
def get_account(api_key, auth_uri):
    future = session.get(auth_uri, params={'api_key': api_key})
    return future.result()


def check_auth_response(api_response):
    if api_response is None or api_response.status_code // 100 != 2:
        return None
    try:
        return api_response.json()
    except ValueError:
        logger.exception(
            'Invalid response from API key management service, received: %s', api_response.encode()
        )
        return None


class User(object):

    def __init__(self, authorized=False, user_id=None, max_artifact_size=DEFAULT_FALLBACK_SIZE):
        self.authorized = authorized
        self.max_artifact_size = max_artifact_size
        self.user_id = user_id if authorized else None

    @classmethod
    def from_api_key(cls, api_key):
        config = app.config['POLYSWARMD']

        auth_uri = f'{config.auth_uri}/communities/{config.community}/auth'

        r = get_auth(api_key, auth_uri)
        j = check_auth_response(r)
        if j is None:
            return cls(
                authorized=False, user_id=None, max_artifact_size=config.fallback_max_artifact_size
            )

        anonymous = j.get('anonymous', True)
        user_id = j.get('user_id') if not anonymous else None

        # Get account features
        account_uri = f'{config.auth_uri}/accounts'
        r = get_account(api_key, account_uri)
        j = check_auth_response(r)
        if j is None:
            return cls(
                authorized=True,
                user_id=user_id,
                max_artifact_size=config.fallback_max_artifact_size
            )

        max_artifact_size = next((
            f['base_uses']
            for f in j.get('account', {}).get('features', [])
            if f['tag'] == 'max_artifact_size'
        ), config.fallback_max_artifact_size)

        return cls(authorized=True, user_id=user_id, max_artifact_size=max_artifact_size)

    @property
    def anonymous(self):
        return self.user_id is None

    def __bool__(self):
        config = app.config['POLYSWARMD']
        return config.require_api_key and self.authorized


@app.route('/status')
def status():
    config = app.config['POLYSWARMD']
    session = app.config['REQUESTS_SESSION']

    ret = {}

    ret['community'] = config.community

    ret['artifact_services'] = {
        config.artifact_client.name.lower(): {
            'reachable': is_service_reachable(session, config.artifact_client.reachable_endpoint),
        }
    }

    if config.auth_uri:
        ret['auth'] = {
            'reachable': is_service_reachable(session, f"{config.auth_uri}/communities/public"),
        }

    for name, chain in config.chains.items():
        ret[name] = {
            'reachable': is_service_reachable(session, f"{chain.eth_uri}", is_ethereum=True),
        }

        if ret[name]['reachable']:
            ret[name]['syncing'] = chain.w3.eth.syncing is not False
            ret[name]['block'] = chain.w3.eth.blockNumber

    return success(ret)


@app.before_request
def before_request():
    g.user = User()

    config = app.config['POLYSWARMD']

    if not config.require_api_key:
        return

    # Ignore prefix if present
    try:
        api_key = request.headers.get('Authorization').split()[-1]
    except Exception:
        # exception == unauthenticated
        return whitelist_check(request.path)

    if api_key:
        g.user = User.from_api_key(api_key)
        if not g.user:
            return whitelist_check(request.path)

    size = request.content_length
    if size is not None and size > g.user.max_artifact_size * 256:
        return failure('Payload too large', 413)


def whitelist_check(path):
    # Want to be able to whitelist unauthenticated routes, everything requires auth by default
    return None if path in AUTH_WHITELIST else failure('Unauthorized', 401)


@app.after_request
def after_request(response):
    eth_address = getattr(g, 'eth_address', None)
    user = getattr(g, 'user', None)

    if response.status_code == 200:
        logger.info(
            '%s %s %s %s %s %s', datetime.datetime.now(), request.method, response.status_code,
            request.path, eth_address, user.user_id
        )
    else:
        logger.error(
            '%s %s %s %s %s %s: %s', datetime.datetime.now(), request.method, response.status_code,
            request.path, eth_address, user.user_id, response.get_data()
        )

    return response
