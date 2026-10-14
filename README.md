# conf-valkey-cluster

[中文](README.zh.md)

A six-node Valkey Cluster for local development on **macOS + OrbStack**: three primaries, each with one replica. Uses host networking and loopback addresses. Other environments are untested; this is not a production deployment.

## Quick start

Requires running OrbStack, Docker Compose, and Python 3.10+.

```bash
git clone https://github.com/sincerefly/conf-valkey-cluster.git
cd conf-valkey-cluster
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
chmod +x init.sh start.sh stop.sh test.sh

./init.sh       # Create the cluster, or verify an existing one
./stop.sh       # Stop containers; keep data
./start.sh      # Restart an initialized cluster
```

Scripts use `.venv/bin/python` automatically; activation is not required. Use the scripts rather than `docker compose up` to retain startup checks.

| Setting | Default |
| --- | --- |
| Image | `valkey/valkey:7.2.14-alpine` |
| Client ports | `7100–7105` |
| Cluster bus ports | `17100–17105` |
| Data | `./data/local/node-0` through `node-5` (AOF enabled) |
| Compose project | `valkey-cluster` |

## Connect and check

Run from the repository directory:

```bash
# Read-only health check across all six nodes
.venv/bin/python redis_cluster_test.py --health

# Read/write check across all three primaries
.venv/bin/python redis_cluster_test.py

# Optional, if redis-cli is installed
redis-cli -c -h 127.0.0.1 -p 7100

# Status and logs
docker compose ps
docker compose logs --tail=100
```

Read/write checks use unique temporary keys, delete them afterward, and set a 60-second TTL. Checks return nonzero on failure; use `--timeout 30` to change the default 60-second deadline per phase. A failed startup check may leave containers running—inspect the logs before retrying.

## Custom configuration

Export overrides in your shell, not in `.env`. For a separate cluster:

```bash
export VALKEY_IMAGE=valkey/valkey:9.1.2-alpine
export VALKEY_BASE_PORT=7200
export VALKEY_DATA_DIR="$PWD/data/valkey-9.1.2"
export COMPOSE_PROJECT_NAME=valkey-cluster-9-1-2

./init.sh
.venv/bin/python redis_cluster_test.py --health
./stop.sh

unset VALKEY_IMAGE VALKEY_BASE_PORT VALKEY_DATA_DIR COMPOSE_PROJECT_NAME
```

The base port selects six consecutive client ports; bus ports are client ports + 10000. Keep the same environment for later checks and start/stop commands. Separate clusters need distinct projects, ports, and data directories. Scripts accept short image tags; raw Compose commands require full image names. Custom port calculation is handled by the scripts, not raw Compose.

**Keep existing data safe:** changing the image or base port requires a new data directory once persistent files exist. Back up before migrating; scripts do not upgrade, reset, or migrate data. Existing `data/7000`–`data/7005` directories and the old deployment are not managed by the new defaults.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
./test.sh                          # Test 7.2.14-alpine and 9.1.2-alpine
./test.sh 9.1.2-alpine              # Test a specific version
```

Integration tests use a temporary project and data directory on ports `27100–27105` and `37100–37105`. Override the base with `VALKEY_TEST_BASE_PORT` if needed. They check repeated initialization, host read/write access, and persistence after restart. Cleanup only removes test data after containers stop successfully; cleanup failure preserves it and fails the test. Both default versions have been tested on OrbStack; this does not verify upgrades of existing data.
