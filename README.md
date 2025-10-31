# conf-valkey-cluster

Docker Compose configuration for Valkey cluster (Multi-Version Support)

**Testing with OrbStack & macOS**

## Usage

### Initialize Cluster

```bash
# Using default Valkey 7.2-alpine
$ chmod +x ./init.sh

$ ./init.sh
```

#### Other Valkey Versions

The script supports layered simplification for `VALKEY_IMAGE`:

```bash
# Simplified: Only specify version tag (auto-adds valkey/valkey: prefix)
$ VALKEY_IMAGE=8.0 ./init.sh              # → valkey/valkey:8.0
$ VALKEY_IMAGE=8.0-alpine ./init.sh       # → valkey/valkey:8.0-alpine
$ VALKEY_IMAGE=8.1-alpine ./init.sh       # → valkey/valkey:8.1-alpine
$ VALKEY_IMAGE=9.0 ./init.sh              # → valkey/valkey:9.0
$ VALKEY_IMAGE=7.2 ./init.sh              # → valkey/valkey:7.2

# Full image name is also supported (unchanged)
$ VALKEY_IMAGE=valkey/valkey:8.0-alpine ./init.sh
```

#### Supported Versions

- `valkey/valkey:7.2-alpine` (default)
- `valkey/valkey:8.0-alpine`
- `valkey/valkey:8.1-alpine`
- `valkey/valkey:9.0-alpine`

For other versions and variants, see: [Docker Hub - valkey/valkey](https://hub.docker.com/r/valkey/valkey/)


### Manual Start & Stop

```bash
# Using default version
docker compose up -d
docker compose down

# Or specify a version (simplified or full format)
VALKEY_IMAGE=8.0 docker compose up -d
VALKEY_IMAGE=8.0-alpine docker compose up -d
VALKEY_IMAGE=8.0 docker compose down

# Full format is also supported
VALKEY_IMAGE=valkey/valkey:8.0-alpine docker compose up -d
```

### Connect

```bash
$ docker inspect valkey-7000 | grep IPAddress
"Secondary**IPAddress**es": null,
"**IPAddress**": "",
	"**IPAddress**": "192.168.97.2",
         
                    
$ redis-cli -c -h 192.168.97.2 -p 7000 ping
PONG
```

Or using local DNS (requires OrbStack)

```bash
$ redis-cli -c -h valkey-7000.valkey-cluster.orb.local -p 7000 ping
PONG
```

## Testing

### Multi-Version Testing Script

Use `test.sh` to automatically test multiple Valkey versions:

```bash
# Test all configured versions sequentially
$ chmod +x ./test.sh
$ ./test.sh
```

The script will:
1. Deploy each version using `init.sh`
2. Print version information
3. Check cluster health
4. Clean up before testing the next version

### Customize Test Versions

Edit `TEST_VERSIONS` in `test.sh` to test specific versions:

```bash
TEST_VERSIONS=("7.2-alpine" "8.0-alpine" "8.1-alpine" "9.0-alpine")
```

### Test Options

```bash
# By default, data directories are cleaned between tests
./test.sh

# Skip data directory cleanup (if you want to preserve data)
CLEANUP_DATA=false ./test.sh

# Adjust wait time between deployment and health check (default: 10s)
TEST_WAIT_TIME=15 ./test.sh

# Combine options
CLEANUP_DATA=false TEST_WAIT_TIME=20 ./test.sh
```
