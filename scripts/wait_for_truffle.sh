#!/bin/sh

set -e

create_config() {
  response=$(curl --silent "$CONSUL/v1/kv/config")
  config_blob=$(echo $response | jq .[0].Value)
  config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  python -c "import yaml, json; print(yaml.dump($config_json, default_flow_style=False))" > /etc/polyswarmd/polyswarmd.yml

}

create_contract_abi() {
  response=$(curl --silent "$CONSUL/v1/kv/$1")
  config_blob=$(echo $response | jq .[0].Value)
  config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  echo $config_json > "/etc/polyswarmd/contracts/$1.json"

}

while getopts ":pw" opt; do
  case ${opt} in
    p ) # process option a
      mkdir -p /etc/polyswarmd/contracts
      curl --connect-timeout 3 --max-time 10 --retry 60 --retry-delay 3 --output /dev/null --retry-max-time 60 "$CONSUL/v1/kv/config"

      create_contract_abi "BountyRegistry"
      create_contract_abi "NectarToken"
      create_contract_abi "OfferRegistry"
      create_contract_abi "OfferLib"
      create_contract_abi "OfferMultiSig"
      create_contract_abi "ArbiterStaking"
      create_config

      echo "Landed configuration in /etc/polyswarmd, listing"
      ls -alhR /etc/polyswarmd

      ;;

    w )
      until $(curl --output /dev/null --silent --fail "$CONSUL/v1/kv/config") ; do
          >&2 echo "The migration is incomplete - sleeping..."
          sleep 1
      done

      >&2 echo "The migration is complete!"

      if [ ! -d /etc/polyswarmd ]
        then mkdir /etc/polyswarmd
      fi

      if [ ! -d /etc/polyswarmd/contracts ]
        then mkdir /etc/polyswarmd/contracts
      fi

      create_contract_abi "BountyRegistry"
      create_contract_abi "NectarToken"
      create_contract_abi "OfferRegistry"
      create_contract_abi "OfferLib"
      create_contract_abi "OfferMultiSig"
      create_contract_abi "ArbiterStaking"
      create_config

      >&2 echo "New configs created"
      ;;
  esac
done

shift $(expr $OPTIND - 1 )
cmd="$@"
echo "gonna run"
echo $cmd
exec $cmd

echo "Fin"

