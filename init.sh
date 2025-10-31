#!/bin/bash
set -e

# 配置变量
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-valkey-cluster-72}
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
        if docker compose exec -T $service valkey-cli -p $port ping 2>/dev/null | grep -q "PONG"; then
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
    if docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster info | grep -q "cluster_state:ok"; then
        log "Cluster is healthy"
        return 0
    else
        log "WARNING: Cluster may not be fully healthy"
        return 1
    fi
}

main() {
    log "Starting Valkey Cluster initialization..."
    
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
        valkey-7000:7000 \
        valkey-7001:7001 \
        valkey-7002:7002 \
        valkey-7003:7003 \
        valkey-7004:7004 \
        valkey-7005:7005 \
        --cluster-replicas 1 --cluster-yes
    
    log "Waiting for cluster to stabilize..."
    sleep 10
    
    if check_cluster_health; then
        log "Valkey cluster initialized successfully!"
        log "Cluster nodes:"
        docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster nodes
    else
        log "Cluster initialized with warnings. Please check cluster status."
        exit 1
    fi
}

# 运行主函数
main "$@"