import os
import sys
import yaml
import time

eth_uri = {}
ipfs_uri = ''
network = ''
config_location = ''

nectar_token_address = {}
bounty_registry_address = {}
erc20_relay_address = {}
offer_registry_address = {}
chain_id = {}
free = False

CONFIG_LOCATIONS = ['/etc/polyswarmd', '~/.config/polyswarmd']

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
    global eth_uri, ipfs_uri, network, config_location, nectar_token_address, \
            bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id, free

    for config_location in CONFIG_LOCATIONS:
        config_location = os.path.expanduser(config_location)
        config_file = os.path.join(config_location, 'polyswarmd.yml')
        if os.path.isfile(config_file):
            break

    if not os.path.isfile(config_file):
        # TODO: What to do here
        print("MISSING CONFIG")
        sys.exit(-1)

    with open(config_file, 'r') as f:
        y = yaml.load(f.read())
        ipfs_uri = y['ipfs_uri']
        if 'free' in y:
            free = y['free']

        home = y['homechain']
        eth_uri['home'] = home['eth_uri']
        nectar_token_address['home'] = home['nectar_token_address']
        bounty_registry_address['home'] = home['bounty_registry_address']
        erc20_relay_address['home'] = home['erc20_relay_address']
        offer_registry_address['home'] = home[
            'offer_registry_address']  # only on home chain
        chain_id['home'] = home['chain_id']

        side = y['sidechain']
        eth_uri['side'] = side['eth_uri']
        nectar_token_address['side'] = side['nectar_token_address']
        bounty_registry_address['side'] = side['bounty_registry_address']
        erc20_relay_address['side'] = side['erc20_relay_address']
        chain_id['side'] = side['chain_id']


def set_config(**kwargs):
    """
    Set up config from arguments for testing purposes
    """
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id, free
    eth_uri = {
        'home': kwargs.get('eth_uri', 'http://localhost:8545'),
        'side': kwargs.get('eth_uri', 'http://localhost:7545'),
    }
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
    free = kwargs.get('free', False)

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
