FROM python:3.5-jessie
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app
COPY requirements.txt ./

# Required for pycrypto
RUN set -x && \
    apt-get update && apt-get install -y \
        libgmp-dev && \
    rm -rf /var/lib/apt/lists/*

RUN set -x && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN set -x && pip install pyinstaller
