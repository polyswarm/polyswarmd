#!/bin/bash

root="${0%/*}/.."
srcpath=$(realpath "$root/src/polyswarmd")

main() {
    cd "$root"

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
    elif [[ "$1" = "--stubs" ]]; then
        gen_stubs
    else
        cat <<EOF
Usage:
 $0 [options]

Options:
  -l          Lint $srcpath with mypy, isort, yapf, flake8 and run doctests.
  -i          Apply destructive formatting with isort & yapf
  --stubs     Generate mypy type stubs for websocket message clases from their JSONSchema
EOF
    fi
}


lint() {
    local -i ret=0
    # Bash make binary manipulation a hassle, so we manually increment
    # to emulate setting flags for which lint-task failed.
    if ! mypy; then
        ret+=1
    fi
    if ! yapf -r -d "$srcpath"; then
        ret+=2
    fi
    if ! isort --recursive --diff "$srcpath"; then
        ret+=4
    fi
    if ! flake8 "$srcpath"; then
        ret+=8
    fi
    cd "$srcpath"
    if ! python -m websockets; then
        ret+=16
    fi

    exit $ret
}

gen_stubs() {
    cd "$srcpath"
    python -m websockets.scripts.gen_stubs | yapf
}

inplace_update() {
    yapf -r -i "$srcpath" && isort --recursive "$srcpath"
    exit $?
}


( main "${1:--l}" )
