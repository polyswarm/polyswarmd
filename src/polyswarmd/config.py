import os
import sys
import yaml

eth_uri = {}
ipfs_uri = ''
network = ''
nectar_token_address = {}
bounty_registry_address = {}
erc20_relay_address = {}
chain_id = {}

CONFIG_LOCATIONS = ['/etc/polyswarmd']


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
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, erc20_relay_address, chain_id

    for loc in CONFIG_LOCATIONS:
        config_file = os.path.join(loc, 'polyswarmd.yml')
        if os.path.isfile(config_file):
            break

    if not os.path.isfile(config_file):
        # TODO: What to do here
        print("MISSING CONFIG")
        sys.exit(-1)

    with open(config_file, 'r') as f:
        y = yaml.load(f.read())
        home = y['homechain']
        nectar_token_address['home'] = home['nectar_token_address']
        bounty_registry_address['home'] = home['bounty_registry_address']
        erc20_relay_address['home'] = home['erc20_relay_address']
        chain_id['home'] = home['chain_id']

        side = y['sidechain']
        nectar_token_address['side'] = side['nectar_token_address']
        bounty_registry_address['side'] = side['bounty_registry_address']
        erc20_relay_address['side'] = side['erc20_relay_address']
        chain_id['side'] = side['chain_id']


def set_config(**kwargs):
    """
    Set up config from arguments for testing purposes
    """
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, erc20_relay_address
    eth_uri = {
        'home': kwargs.get('eth_uri', 'http://localhost:8545'),
        'side': kwargs.get('eth_uri', 'http://localhost:7545'),
    }
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
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
