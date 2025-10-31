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
