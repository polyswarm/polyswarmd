FROM python:3.5-jessie
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

WORKDIR /usr/src/app
COPY requirements.txt ./
# RUN env "CFLAGS=-I/usr/local/include -L/usr/local/lib" pip install pycrypto
RUN apt-get update
RUN apt-get install -y libgmp-dev
RUN set -x && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN set -x && pip install .

CMD ["polyswarmd"]
