#!/bin/sh

set -e

cmd="$@"

until [ -e /etc/polyswarmd/.ready ] ; do
  >&2 echo "The migration is incomplete - sleeping..."
  sleep 1
done

>&2 echo "The migration is complete!"

echo $cmd

exec $cmd
