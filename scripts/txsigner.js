const EthereumTx = require('ethereumjs-tx');
const keythereum = require('keythereum');
const WebSocket = require('isomorphic-ws');

const ws = new WebSocket('ws://localhost:31337/transactions');

const DATADIR = '/home/user/.ethereum/priv_testnet';
const ADDRESS = '34e583cf9c1789c3141538eec77d9f0b8f7e89f2';
const PASSWORD = 'password';

const enc_key = keythereum.importFromFile(ADDRESS, DATADIR);
const key = keythereum.recover(PASSWORD, enc_key);

ws.onmessage = msg => {
  // Should do verification of parameters / user confirmation?
  console.log(msg.data);
  const {id, data} = JSON.parse(msg.data);
  const {chainId} = data;
  console.log(data);
  const tx = new EthereumTx(data);
  tx.sign(key);

  console.log({'id': id, 'chainId': chainId, 'data': tx.serialize().toString('hex')});

  ws.send(JSON.stringify({'id': id, 'chainId': chainId, 'data': tx.serialize().toString('hex')}));
};
