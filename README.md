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

#### Using Helper Scripts (Recommended)

The `start.sh` and `stop.sh` scripts support the same layered simplification as `init.sh`:

```bash
# Using default version
./start.sh
./stop.sh

# Using simplified version format
VALKEY_IMAGE=8.0 ./start.sh              # → valkey/valkey:8.0
VALKEY_IMAGE=8.0-alpine ./start.sh       # → valkey/valkey:8.0-alpine
VALKEY_IMAGE=9.0 ./start.sh              # → valkey/valkey:9.0
./stop.sh

# Full image name is also supported
VALKEY_IMAGE=valkey/valkey:8.0-alpine ./start.sh
./stop.sh
```

#### Using Docker Compose Directly

If you use `docker compose` directly, you must provide the full image name:

```bash
# Using default version
docker compose up -d
docker compose down

# Must use full image name format
VALKEY_IMAGE=valkey/valkey:8.0-alpine docker compose up -d
VALKEY_IMAGE=valkey/valkey:8.0-alpine docker compose down
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

> **Note:** The test script will automatically clean data directories (`./data/*`) between version tests by default. This ensures a clean environment for each test. To preserve data during testing, set `CLEANUP_DATA=false`.

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
