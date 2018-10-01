import contextlib
import json
import logging
import os
import socket
import sys
import tempfile
import yaml

from consul import Consul
from consul.base import Timeout
from urllib.parse import urlparse

eth_uri = {}
ipfs_uri = ''
db_uri = ''
require_api_key = False
config_location = ''

nectar_token_address = {}
bounty_registry_address = {}
erc20_relay_address = {}
offer_registry_address = {}
chain_id = {}
free = {}
consul_uri = None

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd', './config']


def whereami():
    """
    Locate this script in the system, taking into account running from a frozen binary
    """
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(__file__))


def wait_for_consul(consul_uri):
    u = urlparse(consul_uri)
    logging.info('Waiting for consul')
    while True:
        with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(1)
            if sock.connect_ex((u.hostname, u.port)) == 0:
                logging.info('Consul available, continuing')
                return
            else:
                logging.info('Consul not available, sleeping')


def fetch_from_consul_or_wait(client, key, recurse=False, index=0):
    # Need new approach for hot-reload, don't block
    logging.info('Fetching key: %s', key)
    while True:
        try:
            index, data = client.kv.get(key, recurse=recurse, index=index, wait='2m')
            if data is not None:
                logging.info('Got: %s', data)
                return data
        except Timeout:
            logging.info('Consul up but key %s not available, retrying...', key)
            continue


def init_config():
    """
    Read config from yaml file
    """
    global eth_uri, ipfs_uri, db_uri, require_api_key, config_location, nectar_token_address, \
        bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id, free, sidechain_name, consul_client
    y = None
    if os.environ.get('CONSUL'):
        consul_uri = os.environ.get('CONSUL')
        consul_token = os.environ.get('CONSUL_TOKEN', None)

        wait_for_consul(consul_uri)

        u = urlparse(consul_uri)

        consul_client = Consul(host=u.hostname, port=u.port, scheme=u.scheme, token=consul_token)
        # TODO document env variable that controls sidechain
        sidechain_name = os.environ['POLY_SIDECHAIN_NAME']

        # TODO schema check json
        y = json.loads(fetch_from_consul_or_wait(consul_client, '{}/config'.format(sidechain_name))['Value'].decode('utf-8'))
        y['homechain'] = json.loads(fetch_from_consul_or_wait(consul_client, '{}/homechain'.format(sidechain_name))['Value'].decode('utf-8'))
        y['sidechain'] = json.loads(fetch_from_consul_or_wait(consul_client, '{}/sidechain'.format(sidechain_name))['Value'].decode('utf-8'))

        # TODO recurse and write contracts.
        # TODO push contracts key to separate dir
        config_location = tempfile.mkdtemp(prefix='polyconfig')
        contract_location = os.path.join(config_location, 'contracts')
        os.mkdir(contract_location)

        filter_k = [x.format(sidechain_name) for x in ['{}/homechain', '{}/sidechain', '{}/config']]
        all_ks = fetch_from_consul_or_wait(consul_client, '{}/'.format(sidechain_name), recurse=True)

        for kvs in [k for k in all_ks if k.get('Key') not in filter_k]:
            potential_contract = json.loads(kvs['Value'].decode('utf-8'))

            # If ABI key exists, write contract
            if potential_contract.get('abi'):
                contract_name = '{}.json'.format(kvs['Key'].lstrip('{}/'.format(sidechain_name)))
                with open(os.path.join(contract_location, contract_name), 'wb') as f:
                    f.write(kvs['Value'])
                    logging.info('Writing contract {}'.format(contract_name))
    else:
        for config_location in CONFIG_LOCATIONS:
            config_location = os.path.abspath(os.path.expanduser(config_location))
            config_file = os.path.join(config_location, 'polyswarmd.yml')
            if os.path.isfile(config_file):
                break

        if not os.path.isfile(config_file):
            logging.error('MISSING CONFIG')
            sys.exit(-1)

        with open(config_file, 'r') as f:
            y = yaml.load(f.read())

    ipfs_uri = y['ipfs_uri']

    # fallback to env variable in case we can't get this out of our config file.
    db_uri = y.get('db_uri', os.environ.get('DB_URI'))
    if db_uri is not None:
        require_api_key = True

    home = y['homechain']
    eth_uri['home'] = home['eth_uri']
    nectar_token_address['home'] = home['nectar_token_address']
    bounty_registry_address['home'] = home['bounty_registry_address']
    erc20_relay_address['home'] = home['erc20_relay_address']
    offer_registry_address['home'] = home['offer_registry_address']
    chain_id['home'] = home['chain_id']
    free['home'] = home.get('free', False)

    side = y['sidechain']
    eth_uri['side'] = side['eth_uri']
    nectar_token_address['side'] = side['nectar_token_address']
    bounty_registry_address['side'] = side['bounty_registry_address']
    erc20_relay_address['side'] = side['erc20_relay_address']
    chain_id['side'] = side['chain_id']
    free['side'] = side.get('free', False)


def set_config(**kwargs):
    """
    Set up config from arguments for testing purposes
    """
    global eth_uri, ipfs_uri, db_uri, require_api_key, nectar_token_address, \
        bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id, free
    eth_uri = {
        'home': kwargs.get('eth_uri', 'http://localhost:8545'),
        'side': kwargs.get('eth_uri', 'http://localhost:7545'),
    }
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
    db_uri = kwargs.get('db_uri', 'sqlite:///tmp/polyswarmd.sqlite')

    free = {
        'home': kwargs.get('free', False),
        'side': kwargs.get('free', False)
    }

    nectar_token_address = {
        'home': kwargs.get('nectar_token_address', ''),
        'side': kwargs.get('nectar_token_address', ''),
    }
    erc20_relay_address = {
        'home': kwargs.get('erc20_relay_address', ''),
        'side': kwargs.get('erc20_relay_address', ''),
    }
    bounty_registry_address = {
        'home': kwargs.get('bounty_registry_address', ''),
        'side': kwargs.get('bounty_registry_address', ''),
    }
    offer_registry_address = {
        'home': kwargs.get('offer_registry_address', ''),
    }
