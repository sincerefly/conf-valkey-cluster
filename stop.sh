#!/bin/bash

# Stop Valkey cluster
# Note: VALKEY_IMAGE normalization is not needed for stop/down commands

echo "Stopping Valkey cluster..."

# Stop and remove containers
docker compose down

echo "Valkey cluster stopped."
