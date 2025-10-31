#!/bin/bash

# Start Valkey cluster with optional version specification
# Supports the same layered simplification as init.sh

# Source common library functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"

# Normalize image name
normalize_valkey_image

# Display version info
echo "Starting Valkey cluster with image: $VALKEY_IMAGE"

# Start containers
docker compose up -d

echo "Valkey cluster started. Use './stop.sh' to stop it."
