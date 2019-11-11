FROM python:3.6-jessie
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
        jq \
        libgmp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN set -x && pip install --no-cache-dir -r requirements.txt
RUN set -x && pip install ujson wsaccel gunicorn

COPY . .
RUN set -x && pip install .


CMD ["gunicorn", "--bind", "0.0.0.0:31337", "-k", "flask_sockets.worker", "-t", "600", "-w", "4", "polyswarmd.wsgi:app()"]
