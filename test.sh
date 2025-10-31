#!/bin/bash
# Don't use set -e, we want to handle errors manually
set -o pipefail

# Test script for multiple Valkey versions
# Tests deployment, prints version info, then cleans up before next version

# Configuration
TEST_VERSIONS=("7.2-alpine" "8.0-alpine" "8.1-alpine" "9.0-alpine")
CLEANUP_DATA=${CLEANUP_DATA:-true}
TEST_WAIT_TIME=${TEST_WAIT_TIME:-10}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] ✓${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] ⚠${NC} $1"
}

print_separator() {
    echo ""
    echo "=========================================="
    echo ""
}

cleanup() {
    log "Cleaning up current deployment..."
    docker compose down -v 2>/dev/null || true
    
    if [ "$CLEANUP_DATA" != "false" ]; then
        log "Removing data directories..."
        rm -rf ./data/* 2>/dev/null || true
    else
        log "Skipping data directory cleanup (CLEANUP_DATA=false)"
    fi
}

test_version() {
    local version=$1
    print_separator
    log "Testing Valkey version: ${GREEN}${version}${NC}"
    log "Image will be: ${GREEN}valkey/valkey:${version}${NC}"
    print_separator
    
    # Export VALKEY_IMAGE for this test
    export VALKEY_IMAGE="$version"
    
    # Initialize cluster
    log "Deploying Valkey cluster..."
    if ./init.sh 2>&1; then
        log_success "Cluster deployed successfully"
        
        # Wait a bit for cluster to stabilize
        log "Waiting ${TEST_WAIT_TIME}s for cluster to stabilize..."
        sleep "$TEST_WAIT_TIME"
        
        # Test cluster health
        log "Checking cluster health..."
        if docker compose exec -T valkey-7000 valkey-cli -p 7000 cluster info 2>/dev/null | grep -q "cluster_state:ok"; then
            log_success "Cluster is healthy"
            
            # Get version info
            log "Valkey version information:"
            docker compose exec -T valkey-7000 valkey-cli -p 7000 INFO server 2>/dev/null | grep -E "redis_version|valkey_version" || true
            
        else
            log_warning "Cluster health check failed or incomplete"
        fi
        
        # Cleanup before next version
        log "Cleaning up for next test..."
        cleanup
        
    else
        log_error "Failed to deploy cluster for version ${version}"
        cleanup
        return 1
    fi
    
    print_separator
    log_success "Test completed for version ${version}"
    print_separator
}

main() {
    log "Starting Valkey multi-version deployment test"
    log "Test versions: ${TEST_VERSIONS[*]}"
    log "Cleanup data: ${CLEANUP_DATA}"
    log "Test wait time: ${TEST_WAIT_TIME}s"
    echo ""
    
    # Check if init.sh exists
    if [ ! -f "./init.sh" ]; then
        log_error "init.sh not found. Please run this script from the project root directory."
        exit 1
    fi
    
    # Make init.sh executable
    chmod +x ./init.sh
    
    # Ensure we start clean
    log "Ensuring clean initial state..."
    cleanup
    
    # Test each version
    local failed_versions=()
    for version in "${TEST_VERSIONS[@]}"; do
        if ! test_version "$version"; then
            failed_versions+=("$version")
        fi
    done
    
    # Summary
    print_separator
    log "Test Summary"
    print_separator
    
    if [ ${#failed_versions[@]} -eq 0 ]; then
        log_success "All versions tested successfully!"
        log "Tested versions: ${TEST_VERSIONS[*]}"
    else
        log_error "Some versions failed: ${failed_versions[*]}"
        log "Successful versions: $(IFS=', '; echo "${TEST_VERSIONS[@]}" | tr ' ' '\n' | grep -vF "$(IFS='|'; echo "${failed_versions[*]}")" | tr '\n' ' ')"
        exit 1
    fi
    
    # Final cleanup
    log "Final cleanup..."
    cleanup
    log_success "All tests completed!"
}

# Run main function
main "$@"
