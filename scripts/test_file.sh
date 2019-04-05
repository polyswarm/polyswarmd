#! /bin/bash

echo foo > foo
echo bar > bar

curl --trace-ascii - \
    -H "Authorization: $STAGE_KEY" \
    -F file=@foo \
    https://gamma-polyswarmd.stage.polyswarm.network/artifacts?account=0x0000000000000000000000000000000000000000

rm foo bar
