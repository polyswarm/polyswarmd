import os
import sys
import yaml

from dotenv import load_dotenv

eth_uri = dict()
ipfs_uri = ''
network = ''
nectar_token_address = dict()
bounty_registry_address = dict()
chain_id = dict()

def whereami():
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))

    return os.path.dirname(os.path.abspath(__file__))


def init_config():
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address, chainId

    load_dotenv(dotenv_path=os.path.join(whereami(), '.env'))

    eth_uri['home'] = os.environ.get('HOME_ETH_URI', 'http://localhost:8545')
    eth_uri['side'] = os.environ.get('SIDE_ETH_URI', 'http://localhost:8540')
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
        chain_id['home'] = os.environ.get('HOME_CHAIN_ID', home['chain_id'])

        side = y['sidechain']
        nectar_token_address['side'] = os.environ.get('SIDE_NECTAR_TOKEN_ADDRESS', side['nectar_token_address'])
        bounty_registry_address['side'] = os.environ.get('SIDE_BOUNTY_REGISTRY_ADDRESS', side['bounty_registry_address'])
        chain_id['side'] = os.environ.get('SIDE_CHAIN_ID', side['chain_id'])

def set_config(**kwargs):
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address

    eth_uri = kwargs.get('eth_uri', 'http://localhost:8545')
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
    network = kwargs.get('network', 'test')
    nectar_token_address = kwargs.get('nectar_token_address', '')
    bounty_registry_address = kwargs.get('bounty_registry_address', '')
