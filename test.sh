#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"

# Ignore the user's deployment identity and storage. Only our mktemp directory is disposable.
export COMPOSE_PROJECT_NAME="valkey-test-$$-$RANDOM"
export VALKEY_BASE_PORT="${VALKEY_TEST_BASE_PORT:-27100}"
setup
test_root=$(mktemp -d "${TMPDIR:-/tmp}/valkey-test.XXXXXXXX")
export VALKEY_DATA_DIR="$test_root/0"

cleanup() {
    local status=$?
    trap - EXIT
    if compose down; then
        rm -rf -- "$test_root"
    else
        echo "ERROR: cleanup failed; preserving $test_root (project $COMPOSE_PROJECT_NAME)" >&2
        status=1
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ "$#" -eq 0 ]; then
    set -- 7.2.14-alpine 9.1.2-alpine
fi

index=0
for image in "$@"; do
    export VALKEY_IMAGE="$image"
    export VALKEY_DATA_DIR="$test_root/$index"
    setup
    printf '\nTesting %s (project %s, data %s)\n' "$VALKEY_IMAGE" "$COMPOSE_PROJECT_NAME" "$VALKEY_DATA_DIR"
    bash "$SCRIPT_DIR/init.sh"
    bash "$SCRIPT_DIR/init.sh"
    client

    # Verify persistent identity and a real value survive down/up, not just PING.
    before=$(client --node-id "$VALKEY_BASE_PORT")
    key="cluster-test:$COMPOSE_PROJECT_NAME:$index"
    value="restart-$RANDOM"
    result=$(compose exec -T valkey-0 timeout 10 valkey-cli --raw -c -p "$VALKEY_BASE_PORT" SET "$key" "$value" EX 300)
    [ "$result" = OK ]
    compose down
    bash "$SCRIPT_DIR/start.sh"
    after=$(client --node-id "$VALKEY_BASE_PORT")
    [ "$before" = "$after" ]
    result=$(compose exec -T valkey-0 timeout 10 valkey-cli --raw -c -p "$VALKEY_BASE_PORT" GET "$key")
    [ "$result" = "$value" ]
    compose exec -T valkey-0 timeout 10 valkey-cli -c -p "$VALKEY_BASE_PORT" DEL "$key"
    client
    compose down
    index=$((index + 1))
done

echo "All requested versions passed initialization, host routing and persistence checks."
