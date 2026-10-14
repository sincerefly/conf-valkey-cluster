#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
setup
start_nodes
if [ "$(client --state)" = fresh ]; then
    echo "ERROR: cluster is not initialized; run ./init.sh first" >&2
    exit 1
fi
client --health
echo "Valkey cluster started and reachable from the host."
