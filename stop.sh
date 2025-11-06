#!/bin/bash

# Stop Valkey cluster
# Supports the same layered simplification as init.sh and start.sh

# Source common library functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

# Normalize image name
normalize_valkey_image

# Generate COMPOSE_PROJECT_NAME based on VALKEY_IMAGE
generate_compose_project_name

echo "Stopping Valkey cluster..."
echo "Compose project name: $COMPOSE_PROJECT_NAME"

# Stop and remove containers
docker compose down

echo "Valkey cluster stopped."
