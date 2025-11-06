#!/bin/bash
set -e

# Source common library functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

# Configuration variables
CLUSTER_PORTS=(7000 7001 7002 7003 7004 7005)
MAX_ATTEMPTS=30
RETRY_DELAY=2

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_dependencies() {
    if ! command -v docker &> /dev/null; then
        log "ERROR: Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker compose version &> /dev/null; then
        log "ERROR: Docker Compose is not available"
        exit 1
    fi
}

wait_for_node() {
    local service=$1
    local port=$2
    local attempt=1
    
    log "Waiting for $service (port $port) to be ready..."
    
    while [ $attempt -le $MAX_ATTEMPTS ]; do
        # Check from container first (basic connectivity)
        if docker compose exec -T $service valkey-cli -p $port ping 2>/dev/null | grep -q "PONG"; then
            # Also verify from host using 127.0.0.1 as configured in cluster-announce-ip
            if command -v valkey-cli &> /dev/null; then
                if valkey-cli -h 127.0.0.1 -p $port ping 2>/dev/null | grep -q "PONG"; then
                    log "$service is ready (verified from host via 127.0.0.1)"
                    return 0
                fi
            fi
            log "$service is ready"
            return 0
        fi
        log "Attempt $attempt/$MAX_ATTEMPTS: $service not ready yet..."
        sleep $RETRY_DELAY
        attempt=$((attempt + 1))
    done
    
    log "ERROR: $service failed to start within timeout"
    return 1
}

check_cluster_health() {
    log "Checking cluster health..."
    # Verify from host using 127.0.0.1 to match cluster-announce-ip configuration
    if command -v valkey-cli &> /dev/null; then
        # Try from host first (preferred for cluster-announce-ip verification)
        if valkey-cli -h 127.0.0.1 -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
            log "Cluster is healthy (verified from host via 127.0.0.1)"
            return 0
        fi
    fi
    # Fallback to container check
    if docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
        log "Cluster is healthy (verified from container)"
        return 0
    else
        log "WARNING: Cluster may not be fully healthy"
        return 1
    fi
}

main() {
    log "Starting Valkey Cluster initialization..."
    
    # Normalize image name first
    normalize_valkey_image
    
    # Generate COMPOSE_PROJECT_NAME based on VALKEY_IMAGE
    generate_compose_project_name
    
    log "Using Valkey image: $VALKEY_IMAGE"
    log "Compose project name: $COMPOSE_PROJECT_NAME"
    
    check_dependencies
    
    log "Starting containers..."
    docker compose up -d
    
    log "Waiting for all nodes to start..."
    for port in "${CLUSTER_PORTS[@]}"; do
        service="valkey-${port}"
        wait_for_node $service $port
    done
    
    log "Creating Redis cluster..."
    docker compose exec -T valkey-7000 valkey-cli --cluster create \
        127.0.0.1:7000 \
        127.0.0.1:7001 \
        127.0.0.1:7002 \
        127.0.0.1:7003 \
        127.0.0.1:7004 \
        127.0.0.1:7005 \
        --cluster-replicas 1 --cluster-yes
    
    log "Waiting for cluster to stabilize..."
    sleep 10
    
    # Nodes will automatically use cluster-announce-ip (127.0.0.1) to update their addresses
    # This allows host access via 127.0.0.1 while nodes connect via service names internally
    
    if check_cluster_health; then
        log "Valkey cluster initialized successfully!"
        log "Cluster nodes:"
        # Try to show nodes from host using 127.0.0.1, fallback to container
        if command -v valkey-cli &> /dev/null; then
            valkey-cli -h 127.0.0.1 -p 7000 cluster nodes 2>/dev/null || \
            docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster nodes
        else
            docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster nodes
        fi
    else
        log "Cluster initialized with warnings. Please check cluster status."
        exit 1
    fi
}

# Run main function
main "$@"