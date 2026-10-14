#!/bin/bash
# Shared setup for the local six-node OrbStack cluster (macOS Bash 3.2 compatible).

setup() {
    export VALKEY_IMAGE="${VALKEY_IMAGE:-valkey/valkey:7.2.14-alpine}"
    if [[ "$VALKEY_IMAGE" != */* ]]; then
        VALKEY_IMAGE="valkey/valkey:$VALKEY_IMAGE"
    fi
    export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-valkey-cluster}"
    export VALKEY_BASE_PORT="${VALKEY_BASE_PORT:-7100}"
    if [[ ! "$VALKEY_BASE_PORT" =~ ^[1-9][0-9]{3,4}$ ]] ||
        (( VALKEY_BASE_PORT > 55530 )); then
        echo "ERROR: VALKEY_BASE_PORT must be between 1000 and 55530" >&2
        return 1
    fi
    export VALKEY_DATA_DIR="${VALKEY_DATA_DIR:-$SCRIPT_DIR/data/local}"
    if [[ "$VALKEY_DATA_DIR" != /* ]]; then
        VALKEY_DATA_DIR="$SCRIPT_DIR/$VALKEY_DATA_DIR"
    fi
    local index
    for index in 0 1 2 3 4 5; do
        export "PORT_$index=$((VALKEY_BASE_PORT + index))"
        export "BUS_PORT_$index=$((VALKEY_BASE_PORT + index + 10000))"
    done
    if [ -z "${PYTHON:-}" ]; then
        if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
            PYTHON="$SCRIPT_DIR/.venv/bin/python"
        else
            PYTHON=python3
        fi
    fi
}

compose() {
    docker compose --project-directory "$SCRIPT_DIR" --env-file "$SCRIPT_DIR/.env" \
        -f "$SCRIPT_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" "$@"
}

check_dependencies() {
    docker compose version >/dev/null
    docker info >/dev/null
    "$PYTHON" -c 'import redis' || {
        echo "ERROR: install Python dependencies: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
        return 1
    }
}

client() {
    "$PYTHON" "$SCRIPT_DIR/redis_cluster_test.py" --base-port "$VALKEY_BASE_PORT" "$@"
}

start_nodes() {
    check_dependencies
    local index running
    local free_ports=()
    for index in 0 1 2 3 4 5; do
        running=$(compose ps --status running -q "valkey-$index")
        if [ -z "$running" ]; then
            free_ports+=("$((VALKEY_BASE_PORT + index))" "$((VALKEY_BASE_PORT + index + 10000))")
        fi
    done
    if [ "${#free_ports[@]}" -gt 0 ]; then
        client --ports-free "${free_ports[@]}"
    fi

    # Persisted cluster addresses must not be reused with different ports or images.
    local marker="$VALKEY_DATA_DIR/.cluster-settings" previous existing=""
    if [ -d "$VALKEY_DATA_DIR" ]; then
        existing=$(find "$VALKEY_DATA_DIR" -mindepth 1 ! -type d ! -path "$marker" -print -quit)
    fi
    if [ -n "$existing" ]; then
        if [ ! -f "$marker" ]; then
            echo "ERROR: refusing untracked existing data in $VALKEY_DATA_DIR; choose a new VALKEY_DATA_DIR" >&2
            return 1
        fi
        IFS= read -r previous < "$marker"
        if [ "$previous" != "$VALKEY_IMAGE $VALKEY_BASE_PORT" ]; then
            echo "ERROR: $VALKEY_DATA_DIR belongs to $previous; use a new VALKEY_DATA_DIR when changing image or ports" >&2
            return 1
        fi
    else
        # A failed pull can leave only a marker and empty directories; there is no data to protect.
        mkdir -p "$VALKEY_DATA_DIR"
        printf '%s %s\n' "$VALKEY_IMAGE" "$VALKEY_BASE_PORT" > "$marker"
    fi
    printf 'Starting %s with %s on ports %s–%s\n' "$COMPOSE_PROJECT_NAME" "$VALKEY_IMAGE" \
        "$VALKEY_BASE_PORT" "$((VALKEY_BASE_PORT + 5))"
    compose up -d
    client --wait-nodes

    # A PONG alone could come from an unrelated local service or another cluster.
    local container_id host_id
    for index in 0 1 2 3 4 5; do
        container_id=$(compose exec -T "valkey-$index" timeout 10 valkey-cli --raw \
            -p "$((VALKEY_BASE_PORT + index))" CLUSTER MYID)
        host_id=$(client --node-id "$((VALKEY_BASE_PORT + index))")
        if [ "$container_id" != "$host_id" ]; then
            echo "ERROR: host port $((VALKEY_BASE_PORT + index)) does not reach this project's node" >&2
            return 1
        fi
    done
}
