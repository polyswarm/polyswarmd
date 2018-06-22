#! /bin/bash

ACCOUNT="0x34e583cf9c1789c3141538eec77d9f0b8f7e89f2"

curl -H 'Content-Type: application/json' -d '{"amount": "62500000000000000", "uri": "QmYNmQKp6SuaVrpgWRsPTgCQCnpxUYGq76YEKBXuj2N4H6", "duration": 10}' http://localhost:31337/bounties?account=$ACCOUNT
