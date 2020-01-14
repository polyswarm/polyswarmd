import os

import pytest

from polyswarmd.config.polyswarmd import PolySwarmd, Profiler, Artifact


@pytest.fixture(autouse=True)
def test_env():
    original = os.environ
    os.environ = {}
    os.environ.update(original)
    yield
    os.environ = original


def test_fills_in_dict():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': {}}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_replaces_value():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_does_not_change_other_values():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': {'module': 's3', 'class_name': 'IpfsServiceClient'}}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'artifact': {'library': {'module': 'ipfs', 'class_name': 'IpfsServiceClient'}}}


def test_replaces_value_with_dict():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'artifact': {'library': 'test'}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'artifact': {'library': {'module': 'ipfs'}}}


def test_adds_entire_structure():
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    config = {'profiler': {'enabled': True}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'profiler': {'enabled': True}, 'artifact': {'library': {'module': 'ipfs'}}}


def test_set_bool_value():
    os.environ['POLYSWARMD_PROFILER_ENABLED'] = '1'
    config = {'profiler': {'enabled': False}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'profiler': {'enabled': '1'}}
    assert bool(config['profiler']['enabled'])


def test_wipes_out_value():
    os.environ['POLYSWARMD_PROFILER_ENABLED'] = ''
    config = {'profiler': {'enabled': True}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'profiler': {'enabled': ''}}
    assert not bool(config['profiler']['enabled'])


def test_set_multi_word_value():
    os.environ['POLYSWARMD_ARTIFACT_MAX_SIZE'] = "10"
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_MODULE'] = "ipfs"
    os.environ['POLYSWARMD_ARTIFACT_LIBRARY_CLASS_NAME'] = "IpfsServiceClient"
    config = {'artifact': {'library': {}}}
    polyswarmd = PolySwarmd(config)
    polyswarmd.overlay_environment()
    assert config == {'artifact': {"max_size": '10', 'library': {'module': 'ipfs', 'class_name': 'IpfsServiceClient'}}}


def test_type_hints_fix_bool_true():
    os.environ['PROFILER_ENABLED'] = '1'
    os.environ['PROFILER_DB_URI'] = 'asdf'
    config = {}
    profiler = Profiler(config)
    profiler.load()
    assert isinstance(profiler.enabled, bool)
    assert profiler.enabled


def test_type_hints_fix_bool_false():
    os.environ['PROFILER_ENABLED'] = ''
    config = {}
    profiler = Profiler(config)
    profiler.load()
    assert isinstance(profiler.enabled, bool)
    assert not profiler.enabled


def test_type_hints_fix_int():
    os.environ['ARTIFACT_MAX_SIZE'] = "10"
    config = {}
    artifact = Artifact(config)
    artifact.load()
    assert isinstance(artifact.max_size, int)
    assert artifact.max_size == 10


def test_type_hints_fix_no_int():
    config = {}
    artifact = Artifact(config)
    artifact.load()
    assert isinstance(artifact.max_size, int)
