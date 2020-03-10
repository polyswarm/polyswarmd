from flask import current_app as app

from polyswarmd.views.v0.artifacts import artifacts as v0_artifacts
from polyswarmd.views.v0.balances import balances as v0_balances
from polyswarmd.views.v0.bounties import bounties as v0_bounties
from polyswarmd.views.v0.eth import eth as v0_eth
from polyswarmd.views.v0.event_message import init_websockets as v0_init_websockets
from polyswarmd.views.v0.relay import relay as v0_relay
from polyswarmd.views.v0.offers import offers as v0_offers
from polyswarmd.views.v0.staking import staking as v0_staking
from polyswarmd.views.v0.status import status as v0_status

app.register_blueprint(v0_eth, url_prefix='/')
app.register_blueprint(v0_artifacts, url_prefix='/artifacts')
app.register_blueprint(v0_balances, url_prefix='/balances')
app.register_blueprint(v0_bounties, url_prefix='/bounties')
app.register_blueprint(v0_relay, url_prefix='/relay')
app.register_blueprint(v0_offers, url_prefix='/offers')
app.register_blueprint(v0_staking, url_prefix='/staking')
app.register_blueprint(v0_status, url_prefix='/status')

from polyswarmd.views.v1.artifacts import artifacts as v1_artifacts
from polyswarmd.views.v1.balances import balances as v1_balances
from polyswarmd.views.v1.bounties import bounties as v1_bounties
from polyswarmd.views.v1.eth import eth as v1_eth
from polyswarmd.views.v1.event_message import init_websockets as v1_init_websockets
from polyswarmd.views.v1.relay import relay as v1_relay
from polyswarmd.views.v1.offers import offers as v1_offers
from polyswarmd.views.v1.staking import staking as v1_staking
from polyswarmd.views.v1.status import status as v1_status

app.register_blueprint(v1_eth, url_prefix='/v1')
app.register_blueprint(v1_artifacts, url_prefix='/v1/artifacts')
app.register_blueprint(v1_balances, url_prefix='/v1/balances')
app.register_blueprint(v1_bounties, url_prefix='/v1/bounties')
app.register_blueprint(v1_relay, url_prefix='/v1/relay')
app.register_blueprint(v1_offers, url_prefix='/v1/offers')
app.register_blueprint(v1_staking, url_prefix='/v1/staking')
app.register_blueprint(v1_status, url_prefix='/v1/status')

if app.config['POLYSWARMD'].websocket.enabled:
    v0_init_websockets(app)
    v1_init_websockets(app)
