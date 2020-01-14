import os

import pytest

from polyswarmd.config import polyswarmd as polyconfig
from polyswarmd.config.config import Config


@pytest.fixture(autouse=True)
def test_env():
    original = os.environ
    os.environ = {}
    yield
    os.environ = original


def test_fills_in_dict():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': {}}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_replaces_value():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_does_not_change_other_values():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': {'module': 's3', 'class_name': 'IpfsServiceClient'}}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'artifact': {'library': {'module': 'ipfs', 'class_name': 'IpfsServiceClient'}}}


def test_replaces_value_with_dict():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': 'test'}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_adds_entire_structure():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'profiler': {'enabled': True}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'profiler': {'enabled': True}, 'artifact': {'library': {'module': 'ipfs'}}}


def test_set_bool_value():
    os.environ['POLYSWARMD_PROFILER_ENABLED'] = '1'
    config = {'profiler': {'enabled': False}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'profiler': {'enabled': '1'}}
    assert bool(config['profiler']['enabled'])


def test_wipes_out_value():
    os.environ['POLYSWARMD_PROFILER_ENABLED'] = ''
    config = {'profiler': {'enabled': True}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'profiler': {'enabled': ''}}
    assert not bool(config['profiler']['enabled'])


def test_set_multi_word_value():
    os.environ['POLYSWARMD_ARTIFACT_MAX_SIZE'] = "10"
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_CLASS_NAME'] = "IpfsServiceClient"
    config = {'artifact': {'library': {}}}
    Config.overlay('Polyswarmd', config, polyconfig)
    assert config == {'artifact': {"max_size": '10', 'library': {'module': 'ipfs', 'class_name': 'IpfsServiceClient'}}}
