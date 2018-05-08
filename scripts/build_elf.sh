#!/bin/bash
pyinstaller src/polyswarmd/__main__.py -n polyswarmd -y --clean
mkdir -p dist/polyswarmd/truffle
cp -r truffle/build/ dist/polyswarmd/truffle/
cp polyswarmd.yml dist/polyswarmd/
