#!/bin/bash

mkdir -p /tmp/export /tmp/ipfs-data
docker run -d --name ipfs -v /tmp/export:/export -v /tmp/ipfs-data:/data/ipfs -p 4001:4001 -p 127.0.0.1:5001:5001 -p 127.0.0.1:8080:8080 ipfs/go-ipfs:latest
