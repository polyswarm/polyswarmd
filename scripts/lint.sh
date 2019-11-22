#!/bin/bash

root="${0%/*}/.."
srcpath="$root/src/polyswarmd"

main() {
    if [[ "$1" = "-i" ]]; then
        read -p "Do you want to destructively update files in $srcpath (y/n): " -n1
        if [[ $REPLY =~ ^[Yy]$ ]]
        then
            set -euxo pipefail
            inplace_update
        fi
    elif [[ "$1" = "-l" ]]; then
        set -euxo pipefail
        lint
    else
        cat <<EOF
Usage:
 $0 [options]

Options:
  -l				Lint $srcpath with mypy, isort & yapf.
  -i				Apply destructive formatting with isort & yapf
EOF
    fi
}


lint() {
    cd "$root"

    mypy && \
        yapf -r -d "$srcpath" && \
        isort --recursive --diff "$srcpath" && \
        cd "$srcpath/" &&\
        python -m websockets

    exit $?
}

inplace_update() {
    cd "$root"

    yapf -r -i "$srcpath"
    isort --recursive "$srcpath"

    exit $?
}


( main "${1:--l}" )
