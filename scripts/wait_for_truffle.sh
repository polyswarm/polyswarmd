#!/bin/bash

set -e

if [ -e $CONSUL_TOKEN ]; then
  header="X-Consul-Token: $CONSUL_TOKEN"
else
  header=""
fi

create_config() {
  response=$(curl --header $header --silent "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/config")
  config_blob=$(echo $response | jq .[0].Value)
  config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  response=$(curl --header $header --silent "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/homechain")
  config_blob=$(echo $response | jq .[0].Value)
  homechain_config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  response=$(curl --header $header --silent "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/sidechain")
  config_blob=$(echo $response | jq .[0].Value)
  sidechain_config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  combined_configs_json=$(python -c "import json; print({**$config_json,**{'homechain':$homechain_config_json },**{'sidechain':$sidechain_config_json}})")
  python -c "import yaml; print(yaml.dump($combined_configs_json, default_flow_style=False))" > /etc/polyswarmd/polyswarmd.yml

}

create_contract_abi() {
  response=$(curl --header $header --silent "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/$1")
  config_blob=$(echo $response | jq .[0].Value)
  config_json=$(echo $config_blob | tr -d '"' | base64 --decode)

  echo $config_json > "/etc/polyswarmd/contracts/$1.json"

}

check_config() {
  curl --header $header --silent --fail "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/config" | grep -vq Value
  return $?
}


while getopts ":pw" opt; do
  case ${opt} in
    p ) # process option a
      mkdir -p /etc/polyswarmd/contracts
      curl --header $header --connect-timeout 3 --max-time 10 --retry 60 --retry-delay 3 --retry-max-time 60 "$CONSUL/v1/kv/$POLY_SIDECHAIN_NAME/config"

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
      until check_config; do
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

