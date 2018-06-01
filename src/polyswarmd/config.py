import os
import sys
import yaml

from dotenv import load_dotenv

eth_uri = dict()
ipfs_uri = ''
network = ''
nectar_token_address = dict()
bounty_registry_address = dict()
erc20_relay_address = dict()
offer_registry_address = dict()
chain_id = dict()

def whereami():
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(__file__))


def init_config():
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, erc20_relay_address, offer_registry_address, chain_id

    load_dotenv(dotenv_path=os.path.join(whereami(), '.env'))

    eth_uri['home'] = os.environ.get('HOME_ETH_URI', 'http://localhost:8545')
    eth_uri['side'] = os.environ.get('SIDE_ETH_URI', 'http://localhost:7545')
    ipfs_uri = os.environ.get('IPFS_URI', 'http://localhost:5001')
    network = os.environ.get('POLYSWARMD_NETWORK', None)

    config_file = 'polyswarmd.yml' if not network else 'polyswarmd.{}.yml'.format(
        network)
    config_file = os.path.abspath(
        os.path.join(whereami(), 'config', config_file))

    with open(config_file, 'r') as f:
        y = yaml.load(f.read())
        home = y['homechain']
        nectar_token_address['home'] = os.environ.get('HOME_NECTAR_TOKEN_ADDRESS', home['nectar_token_address'])
        bounty_registry_address['home'] = os.environ.get('HOME_BOUNTY_REGISTRY_ADDRESS', home['bounty_registry_address'])
        erc20_relay_address['home'] = os.environ.get('HOME_ERC20_RELAY_ADDRESS', home['erc20_relay_address'])
        offer_registry_address['home'] = os.environ.get('OFFER_REGISTRY_ADDRESS', home['offer_registry_address']) # only on home chain
        chain_id['home'] = os.environ.get('HOME_CHAIN_ID', home['chain_id'])

        side = y['sidechain']
        nectar_token_address['side'] = os.environ.get('SIDE_NECTAR_TOKEN_ADDRESS', side['nectar_token_address'])
        bounty_registry_address['side'] = os.environ.get('SIDE_BOUNTY_REGISTRY_ADDRESS', side['bounty_registry_address'])
        erc20_relay_address['side'] = os.environ.get('SIDE_ERC20_RELAY_ADDRESS', side['erc20_relay_address'])
        chain_id['side'] = os.environ.get('SIDE_CHAIN_ID', side['chain_id'])

def set_config(**kwargs):
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, erc20_relay_address
    eth_uri = dict()
    eth_uri['home'] = kwargs.get('eth_uri', 'http://localhost:8545')
    eth_uri['side'] = kwargs.get('eth_uri', 'http://localhost:7545')
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
    network = kwargs.get('network', 'test')
    nectar_token_address = dict()
    nectar_token_address['home'] = kwargs.get('nectar_token_address', '')
    nectar_token_address['side'] = kwargs.get('nectar_token_address', '')
    erc20_relay_address = dict()
    erc20_relay_address['home'] = kwargs.get('erc20_relay_address', '')
    erc20_relay_address['side'] = kwargs.get('erc20_relay_address', '')
    bounty_registry_address = dict()
    bounty_registry_address['home'] = kwargs.get('bounty_registry_address', '')
    bounty_registry_address['side'] = kwargs.get('bounty_registry_address', '')
    offer_registry_address = dict()
    offer_registry_address['home'] = kwargs.get('offer_registry_address', '')
