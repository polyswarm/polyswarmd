#!/bin/sh

set -e



while getopts ":p" opt; do
  case ${opt} in
    p ) # process option a
      mkdir -p /etc/polyswarmd
      CONF_TAR=/etc/polyswarmd/polyswarmd.tar
      curl --connect-timeout 3 --max-time 10 --retry 60 --retry-delay 3 --retry-max-time 60 $CONTRACTS_URL > $CONF_TAR

      tar -xf $CONF_TAR -C /etc/polyswarmd
      echo "Landed configuration in /etc/polyswarmd, listing"
      ls -alhR /etc/polyswarmd

      ;;

    \? )
      until [ -e /etc/polyswarmd/.ready ] ; do
          >&2 echo "The migration is incomplete - sleeping..."
          sleep 1
      done

      >&2 echo "The migration is complete!"


      ;;
  esac
done

shift $(expr $OPTIND - 1 )
cmd="$@"
echo "gonna run"
echo $cmd
exec $cmd

echo "Fin"

