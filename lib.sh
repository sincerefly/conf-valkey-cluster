#!/bin/bash
# Common library functions for Valkey cluster scripts

# Normalize VALKEY_IMAGE environment variable
# Supports layered simplification strategy:
# - If empty: use default valkey/valkey:7.2-alpine
# - If contains '/': treat as full image name, use as-is
# - If no '/': treat as version tag, add valkey/valkey: prefix
# Examples:
#   8.0              → valkey/valkey:8.0
#   8.0-alpine       → valkey/valkey:8.0-alpine
#   7.2              → valkey/valkey:7.2
#   valkey/valkey:8.0-alpine → valkey/valkey:8.0-alpine (unchanged)
normalize_valkey_image() {
    if [ -z "$VALKEY_IMAGE" ]; then
        # Use default value if not set
        export VALKEY_IMAGE="valkey/valkey:7.2-alpine"
    elif [[ "$VALKEY_IMAGE" == *"/"* ]]; then
        # Contains '/', treat as full image name, use as-is
        export VALKEY_IMAGE="$VALKEY_IMAGE"
    else
        # No '/', treat as version tag, add valkey/valkey: prefix
        export VALKEY_IMAGE="valkey/valkey:$VALKEY_IMAGE"
    fi
}

# Generate COMPOSE_PROJECT_NAME from VALKEY_IMAGE
# Extracts version number and converts to format: valkey-cluster-XX
# Examples:
#   valkey/valkey:8.0-alpine → valkey-cluster-80
#   valkey/valkey:7.2-alpine → valkey-cluster-72
#   valkey/valkey:9.0        → valkey-cluster-90
generate_compose_project_name() {
    if [ -z "$VALKEY_IMAGE" ]; then
        export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-valkey-cluster}"
        return
    fi
    
    # Extract version tag from VALKEY_IMAGE
    # Handle both formats: valkey/valkey:8.0-alpine and 8.0-alpine
    local version_tag
    if [[ "$VALKEY_IMAGE" == *":"* ]]; then
        # Full image format: extract part after ':'
        version_tag="${VALKEY_IMAGE##*:}"
    else
        # Already just the tag
        version_tag="$VALKEY_IMAGE"
    fi
    
    # Extract major.minor version (e.g., 8.0 from 8.0-alpine)
    # Remove suffix after first non-digit/dot character
    local version_number
    version_number=$(echo "$version_tag" | sed -E 's/^([0-9]+\.[0-9]+).*/\1/' | head -n1)
    
    # If extraction failed, use fallback
    if [ -z "$version_number" ] || [[ ! "$version_number" =~ ^[0-9]+\.[0-9]+$ ]]; then
        export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-valkey-cluster}"
        return
    fi
    
    # Remove dot to create compact version (8.0 → 80)
    local compact_version="${version_number//./}"
    
    # Set COMPOSE_PROJECT_NAME (only if not already set by user)
    if [ -z "$COMPOSE_PROJECT_NAME" ] || [ "$COMPOSE_PROJECT_NAME" = "valkey-cluster" ]; then
        export COMPOSE_PROJECT_NAME="valkey-cluster-${compact_version}"
    fi
}
