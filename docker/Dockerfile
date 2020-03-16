FROM pypy:3-7-stretch
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
        jq \
        libgmp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN set -x && pip install --no-cache-dir -r requirements.txt

COPY . .
COPY ./config/polyswarmd.yml /etc/polyswarmd/polyswarmd.yml
RUN set -x && pip install .

# You can set log format and level in command line by e.g. `polyswarmd.wsgi:app(log_format='text', log_level='WARNING')`
ENV GUNICORN_CMD_ARGS="--bind 0.0.0.0:31337 -k flask_sockets.worker -w 4"
CMD ["gunicorn", "polyswarmd.wsgi:app()"]
