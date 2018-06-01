#!/bin/bash
pyinstaller src/polyswarmd/__main__.py -n polyswarmd -y --clean
mkdir -p dist/polyswarmd/truffle
cp -r truffle/build/ dist/polyswarmd/truffle/
cp -r src/polyswarmd/config dist/polyswarmd/
rm -rf polyswarmd.spec build
