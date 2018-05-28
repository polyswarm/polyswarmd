#! /bin/bash

echo foo > foo
echo bar > bar

curl -v \
    -F file=@foo \
    -F file=@bar \
    http://localhost:31337/artifacts

rm foo bar
