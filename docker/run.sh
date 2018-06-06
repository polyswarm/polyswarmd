#!/bin/sh

cd /usr/src/app/polyswarm-relay/truffle
truffle migrate --reset

cd /usr/src/app/truffle
truffle migrate --reset

cd /usr/src/app
polyswarmd
