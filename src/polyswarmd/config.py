import json
import logging
import os
import sys
import tempfile
import time
from urllib.parse import urlparse

import yaml
from consul import Consul

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
consul_url = None

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd', './config']


def whereami():
    """
    Locate this script in the system, taking into account running from a frozen binary
    """
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(__file__))




def init_config():
    """
    Read config from yaml file
    """
    global eth_uri, ipfs_uri, db_uri, require_api_key, config_location, nectar_token_address, \
            bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id, free, sidechain_name, consul_o
    y = None
    if os.environ.get("CONSUL"):

        consul_u = os.environ.get("CONSUL")
        u = urlparse(consul_u)
        # todo assuming http
        # todo document env variable that controls sidechain
        consul_o = Consul(host=u.hostname, port=u.port, token=os.environ.get("CONSUL_HTTP_TOKEN", None))
        sidechain_name = os.environ['POLY_SIDECHAIN_NAME']
        # wait on this key to appear
        # todo schema check json
        base_config = json.loads(consul_o.kv.get("{}/config".format(sidechain_name), index=0, wait='2m')[1]['Value'].decode('utf-8'))
        base_config['homechain'] = json.loads(consul_o.kv.get("{}/homechain".format(sidechain_name), index=0, wait='2m')[1]['Value'].decode('utf-8'))
        base_config['sidechain'] = json.loads(consul_o.kv.get("{}/sidechain".format(sidechain_name), index=0, wait='2m')[1]['Value'].decode('utf-8'))
        # todo recurse and write contracts.
        y = base_config
        # todo push contracts key to separate dir
        filter_k = [x.format(sidechain_name) for x in ["{}/homechain", "{}/sidechain", "{}/config"]]
        idx, all_ks = consul_o.kv.get("{}/".format(sidechain_name), recurse=True)
        contract_location = None
        for config_location in CONFIG_LOCATIONS:
            potential = os.path.abspath(os.path.expanduser(config_location))
            if os.path.exists(potential):
                contract_location = os.path.join(potential, "contracts")
                break

        if contract_location is None:
            # create from last
            config_location = tempfile.mkdtemp(prefix="polyconfig")
            contract_location = os.path.join(config_location, "contracts")
            os.mkdir(contract_location)

        for kvs in filter(lambda k: k.get("Key") not in filter_k, all_ks):
            # check for abi key and assume contract, write.
            potential_contract = json.loads(kvs['Value'].decode('utf-8'))



            if potential_contract.get("abi"):
                # then write it to ContractName.json
                contract_name = "{}.json".format(kvs['Key'].lstrip("{}/".format(sidechain_name)))
                with open(os.path.join(contract_location, contract_name), 'wb') as f:
                    f.write(kvs['Value'])
                    logging.info("Writing contract {}".format(contract_name))
        pass
    else:
        for config_location in CONFIG_LOCATIONS:
            config_location = os.path.abspath(os.path.expanduser(config_location))
            config_file = os.path.join(config_location, 'polyswarmd.yml')
            if os.path.isfile(config_file):
                break

        if not os.path.isfile(config_file):
            logging.error("MISSING CONFIG")
            sys.exit(-1)
    # already done if we've parsed from consul
        with open(config_file, 'r') as f:
            y = yaml.load(f.read())

    ipfs_uri = y['ipfs_uri']
    db_uri = y.get('db_uri')
    # fallback to env variable in case we can't get this out of our config file.
    if db_uri is None:
        db_uri = os.environ.get("DB_URI")

    # require if we've set our DB up.

    if db_uri is not None:
        require_api_key = True

    home = y['homechain']
    eth_uri['home'] = home['eth_uri']
    nectar_token_address['home'] = home['nectar_token_address']
    bounty_registry_address['home'] = home['bounty_registry_address']
    erc20_relay_address['home'] = home['erc20_relay_address']
    offer_registry_address['home'] = home[
        'offer_registry_address']  # only on home chain
    chain_id['home'] = home['chain_id']
    free["home"] = home.get('free', False)

    side = y['sidechain']
    eth_uri['side'] = side['eth_uri']
    nectar_token_address['side'] = side['nectar_token_address']
    bounty_registry_address['side'] = side['bounty_registry_address']
    erc20_relay_address['side'] = side['erc20_relay_address']
    chain_id['side'] = side['chain_id']
    free["side"] = side.get('free', False)


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
