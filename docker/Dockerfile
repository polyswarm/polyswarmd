FROM python:3
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN set -x && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN set -x && pip install .

CMD ["polyswarmd"]
