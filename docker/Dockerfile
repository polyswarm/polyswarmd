FROM python:3.5-jessie
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
        libgmp-dev && apt-get install -y jq

COPY requirements.txt ./

RUN set -x && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN set -x && pip install .

CMD ["polyswarmd"]
