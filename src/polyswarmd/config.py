import os
import sys
import yaml

from dotenv import load_dotenv

eth_uri = ''
ipfs_uri = ''
network = ''
nectar_token_address = ''
bounty_registry_address = ''


def whereami():
    if hasattr(sys, 'frozen') and sys.frozen in ('windows_exe', 'console_exe'):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))


def init_config():
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address

    load_dotenv(dotenv_path=os.path.join(whereami(), '.env'))

    eth_uri = os.environ.get('ETH_URI', 'http://localhost:8545')
    ipfs_uri = os.environ.get('IPFS_URI', 'http://localhost:5001')
    network = os.environ.get('POLYSWARMD_NETWORK', None)

    config_file = 'polyswarmd.yml' if not network else 'polyswarmd.{}.yml'.format(
        network)
    config_file = os.path.abspath(
        os.path.join(whereami(), 'config', config_file))

    with open(config_file, 'r') as f:
        y = yaml.load(f.read())
        nectar_token_address = y['nectar_token_address']
        bounty_registry_address = y['bounty_registry_address']

def set_config(**kwargs):
    global eth_uri, ipfs_uri, network, nectar_token_address, bounty_registry_address

    eth_uri = kwargs.get('eth_uri', 'http://localhost:8545')
    ipfs_uri = kwargs.get('ipfs_uri', 'http://localhost:5001')
    network = kwargs.get('network', 'test')
    nectar_token_address = kwargs.get('nectar_token_address', '')
    bounty_registry_address = kwargs.get('bounty_registry_address', '')
