#!/bin/bash
pyinstaller polyswarmd.py -y --clean
mkdir -p dist/polyswarmd/frontend
cp -r frontend/build/ dist/polyswarmd/frontend/
mkdir -p dist/polyswarmd/truffle
cp -r truffle/build/ dist/polyswarmd/truffle/
cp polyswarmd.cfg dist/polyswarmd/
