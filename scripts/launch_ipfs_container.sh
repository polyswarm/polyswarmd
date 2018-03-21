#!/bin/bash

mkdir -p /tmp/export /tmp/ipfs-data
docker run -d --name ipfs -v /tmp/export:/export -v /tmp/ipfs-data:/data/ipfs -p 8080:8080 -p 4001:4001 -p 127.0.0.1:5001:5001 polyswarm/ipfs:latest
