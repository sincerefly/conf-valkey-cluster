#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
setup
start_nodes

state=$(client --state)
if [ "$state" = fresh ]; then
    endpoints=()
    for index in 0 1 2 3 4 5; do
        endpoints+=("127.0.0.1:$((VALKEY_BASE_PORT + index))")
    done
    compose exec -T valkey-0 timeout 90 valkey-cli --cluster create \
        "${endpoints[@]}" --cluster-replicas 1 --cluster-yes
else
    echo "Existing cluster state found; verifying without resetting data."
fi
client --health
echo "Valkey cluster initialized and reachable from the host."
