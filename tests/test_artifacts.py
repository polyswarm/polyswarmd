import io

import requests_mock
from polyswarmd import app
from tests import client, test_account

ipfs_uri = app.config['POLYSWARMD'].ipfs_uri

def setup_mocks(mock):
    mock.post(
        ipfs_uri + '/api/v0/add',
        text=
        '{"Name":"foo","Hash":"QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6","Size":"12"}\n{"Name":"bar","Hash":"QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM","Size":"12"}\n{"Name":"","Hash":"QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU","Size":"118"}\n'
    )
    mock.get(
        ipfs_uri +
        '/api/v0/ls?arg=QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU',
        text=
        '{"Objects":[{"Hash":"QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU","Links":[{"Name":"bar","Hash":"QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM","Size":12,"Type":2},{"Name":"foo","Hash":"QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6","Size":12,"Type":2}]}]}'
    )
    mock.get(
        ipfs_uri +
        '/api/v0/cat?arg=QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM',
        text='bar')
    mock.get(
        ipfs_uri +
        '/api/v0/cat?arg=QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6',
        text='foo')
    mock.get(
        ipfs_uri +
        '/api/v0/object/stat?arg=QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM',
        text=
        '{"Hash":"QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM","NumLinks":0,"BlockSize":12,"LinksSize":2,"DataSize":10,"CumulativeSize":12}'
    )
    mock.get(
        ipfs_uri +
        '/api/v0/object/stat?arg=QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6',
        text=
        '{"Hash":"QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6","NumLinks":0,"BlockSize":12,"LinksSize":2,"DataSize":10,"CumulativeSize":12}'
    )


def test_post_artifacts(client):
    expected = b'{"result":"QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU","status":"OK"}\n'
    with requests_mock.Mocker() as mock:
        setup_mocks(mock)
        rv = client.post(
            '/artifacts?account={0}'.format(test_account),
            content_type='multipart/form-data',
            data={
                'bar': io.BytesIO(b'bar'),
                'foo': io.BytesIO(b'foo'),
            })

        assert rv.data == expected


def test_get_artifacts_ipfshash(client):
    expected = b'{"result":[{"hash":"QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM","name":"bar"},{"hash":"QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6","name":"foo"}],"status":"OK"}\n'
    with requests_mock.Mocker() as mock:
        setup_mocks(mock)
        rv = client.get(
            '/artifacts/QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU?account={0}'.format(test_account))
        assert rv.data == expected


def test_get_artifacts_ipfshash_id(client):
    expected = (b'bar', b'foo')
    with requests_mock.Mocker() as mock:
        setup_mocks(mock)
        rv = client.get(
            '/artifacts/QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU/0?account={0}'.format(test_account))
        assert rv.data == expected[0]
        rv = client.get(
            '/artifacts/QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU/1?account={0}'.format(test_account))
        assert rv.data == expected[1]


def test_get_artifacts_ipfshash_id_stat(client):
    expected = (
        b'{"result":{"block_size":12,"cumulative_size":12,"data_size":10,"hash":"QmTz3oc4gdpRMKP2sdGUPZTAGRngqjsi99BPoztyP53JMM","links_size":2,"name":"bar","num_links":0},"status":"OK"}\n',
        b'{"result":{"block_size":12,"cumulative_size":12,"data_size":10,"hash":"QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6","links_size":2,"name":"foo","num_links":0},"status":"OK"}\n'
    )
    with requests_mock.Mocker() as mock:
        setup_mocks(mock)
        rv = client.get(
            '/artifacts/QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU/0/stat?account={0}'.format(test_account))
        assert rv.data == expected[0]
        rv = client.get(
            '/artifacts/QmV32WjiHoYMC5xTuiwZMcEFx686M7qKJmbMQ1cSEwkXvU/1/stat?account={0}'.format(test_account))
        assert rv.data == expected[1]
