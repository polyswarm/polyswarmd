#! /bin/bash

echo foo > foo
echo bar > bar

curl --trace-ascii - \
    -F file=@foo \
    -F file=@bar \
    http://localhost:31337/artifacts?account=0x0000000000000000000000000000000000000000

rm foo bar
