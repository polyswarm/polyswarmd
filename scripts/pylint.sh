#! /bin/bash

# cd to repository root directory
cd "${0%/*}/.."

source venv/bin/activate
cd src
python3 $(which pylint) --rcfile=../.pylintrc polyswarmd
