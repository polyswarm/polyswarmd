FROM ubuntu:latest
LABEL maintainer="PolySwarm Developers <info@polyswarm.io>"

RUN apt-get update \
  && apt-get install -y python3-pip python3-dev \
  && cd /usr/local/bin \
  && ln -s /usr/bin/python3 python \
  && pip3 install --upgrade pip

WORKDIR /usr/src/app

# install python requirments
COPY requirements.txt ./
RUN set -x && pip install --no-cache-dir -r requirements.txt

# install node
RUN apt-get install -y curl
RUN curl -sL https://deb.nodesource.com/setup_8.x -o nodesource_setup.sh 
RUN apt-get -y install nodejs
RUN apt-get -y install npm

# copy in the reset of the project
COPY . .

# build and deploy polyswarm-contracts repo
RUN npm install -g truffle
WORKDIR /usr/src/app/truffle/polyswarm-contracts
RUN npm install
RUN truffle migrate --reset

# build and deploy polyswarm-relay repo
WORKDIR /usr/src/app/truffle/polyswarm-relay
RUN npm install
RUN truffle migrate --reset

# build and run polyswarmd
WORKDIR /usr/src/app
RUN set -x && pip install .
CMD ["polyswarmd"]
