"""
   isort:skip_file
"""
from concurrent.futures import ThreadPoolExecutor
from requests_futures.sessions import FuturesSession
from polyswarmd.monkey import patch_all

patch_all()

import datetime

import functools
import logging

from flask import Flask, g, request
from flask_caching import Cache

from polyswarmd.config.polyswarmd import PolySwarmd, DEFAULT_FALLBACK_SIZE

from polyswarmd.utils.profiler import setup_profiler
from polyswarmd.utils.response import success, failure, install_error_handlers

logger = logging.getLogger(__name__)
cache: Cache = Cache(config={"CACHE_TYPE": "simple", "CACHE_DEFAULT_TIMEOUT": 30})

# Set up our app object
app = Flask(__name__)
_config = PolySwarmd.auto()
app.config['POLYSWARMD'] = _config
# Setting this value works even when Content-Length is omitted, we must have it
app.config['MAX_CONTENT_LENGTH'] = _config.artifact.max_size * _config.artifact.limit

session = FuturesSession(executor=ThreadPoolExecutor(4), adapter_kwargs={'max_retries': 2})

session.request = functools.partial(session.request, timeout=10)

app.config['REQUESTS_SESSION'] = session
app.config['CHECK_BLOCK_LIMIT'] = True
app.config['THREADPOOL'] = ThreadPoolExecutor()

install_error_handlers(app)

from polyswarmd.views.v0.eth import misc as v0_misc
from polyswarmd.views.v0.artifacts import artifacts as v0_artifacts
from polyswarmd.views.v0.balances import balances as v0_balances
from polyswarmd.views.v0.bounties import bounties as v0_bounties
from polyswarmd.views.v0.relay import relay as v0_relay
from polyswarmd.views.v0.offers import offers as v0_offers
from polyswarmd.views.v0.staking import staking as v0_staking
from polyswarmd.views.v0.event_message import init_websockets as v0_init_websockets

app.register_blueprint(v0_misc, url_prefix='/')
app.register_blueprint(v0_artifacts, url_prefix='/artifacts')
app.register_blueprint(v0_balances, url_prefix='/balances')
app.register_blueprint(v0_bounties, url_prefix='/bounties')
app.register_blueprint(v0_relay, url_prefix='/relay')
app.register_blueprint(v0_offers, url_prefix='/offers')
app.register_blueprint(v0_staking, url_prefix='/staking')

from polyswarmd.views.v1.eth import misc as v1_misc
from polyswarmd.views.v1.artifacts import artifacts as v1_artifacts
from polyswarmd.views.v1.balances import balances as v1_balances
from polyswarmd.views.v1.bounties import bounties as v1_bounties
from polyswarmd.views.v1.relay import relay as v1_relay
from polyswarmd.views.v1.offers import offers as v1_offers
from polyswarmd.views.v1.staking import staking as v1_staking
from polyswarmd.views.v1.event_message import init_websockets as v1_init_websockets

app.register_blueprint(v1_misc, url_prefix='/v1')
app.register_blueprint(v1_artifacts, url_prefix='/v1/artifacts')
app.register_blueprint(v1_balances, url_prefix='/v1/balances')
app.register_blueprint(v1_bounties, url_prefix='/v1/bounties')
app.register_blueprint(v1_relay, url_prefix='/v1/relay')
app.register_blueprint(v1_offers, url_prefix='/v1/offers')
app.register_blueprint(v1_staking, url_prefix='/v1/staking')

if app.config['POLYSWARMD'].websocket.enabled:
    v0_init_websockets(app)
    v1_init_websockets(app)

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

        auth_uri = f'{config.auth.uri}/communities/{config.community}/auth'

        r = get_auth(api_key, auth_uri)
        j = check_auth_response(r)
        if j is None:
            return cls(
                authorized=False, user_id=None, max_artifact_size=config.artifact.fallback_max_size
            )

        anonymous = j.get('anonymous', True)
        user_id = j.get('user_id') if not anonymous else None

        # Get account features
        account_uri = f'{config.auth.uri}/accounts'
        r = get_account(api_key, account_uri)
        j = check_auth_response(r)
        if j is None:
            return cls(
                authorized=True,
                user_id=user_id,
                max_artifact_size=config.artifact.fallback_max_size
            )

        max_artifact_size = next((
            f['base_uses']
            for f in j.get('account', {}).get('features', [])
            if f['tag'] == 'max_artifact_size'
        ), config.artifact.fallback_max_size)
        return cls(authorized=True, user_id=user_id, max_artifact_size=max_artifact_size)

    @property
    def anonymous(self):
        return self.user_id is None

    def __bool__(self):
        config = app.config['POLYSWARMD']
        return config.auth.require_api_key and self.authorized


@app.route('/status')
def status():
    config = app.config['POLYSWARMD']
    return success(config.status.get_status())


@app.before_request
def before_request():
    g.user = User()

    config = app.config['POLYSWARMD']

    if not config.auth.require_api_key:
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
