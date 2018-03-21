#!/bin/bash

DIR=$HOME/.ethereum/priv_testnet

# cd to script directory
mkdir -p $DIR
cd "${0%/*}"

cp ./genesis.json $DIR
cp -r ./keystore $DIR

geth --datadir $DIR --nodiscover --maxpeers 0 init $DIR/genesis.json
geth --datadir $DIR --nodiscover --maxpeers 0 --mine --minerthreads 1 --rpc --rpcapi "eth,web3,personal,net" --ws --wsaddr "0.0.0.0" --wsport 8546 --wsapi "eth,web3,personal,net" --wsorigins "*"
