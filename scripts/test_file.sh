#! /bin/bash

echo foo > foo
echo bar > bar

curl -v -X POST \
    -F file=@foo \
    -F file=@bar \
    http://localhost:8000/artifacts

rm foo bar
