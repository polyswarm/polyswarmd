#! /bin/bash

curl -v -i -N \
    -H "Connection: Upgrade" \
    -H "Upgrade: websocket" \
    -H "Host: localhost" \
    -H "Origin: http://localhost:31337" \
    -H "Sec-WebSocket-Key: x3JJHMbDL1EzLkh9GBhXDw==" \
    -H "Sec-WebSocket-Version: 13" \
    http://localhost:31337/transactions
