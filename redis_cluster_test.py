#!/usr/bin/env python3
"""Python 3.10+ host-side checks for the six-node local Valkey cluster."""
import argparse
from contextlib import contextmanager
import math
import os
import re
import signal
import socket
import sys
import time
import uuid

from redis import Redis
from redis.backoff import NoBackoff
from redis.cluster import RedisCluster
from redis.crc import key_slot
from redis.exceptions import RedisError, RedisClusterException
from redis.retry import Retry


HOST = "127.0.0.1"
NODE_ID = re.compile(r"[0-9a-f]{40}\Z")


class CheckError(RuntimeError):
    pass


class PhaseTimeout(BaseException):
    # RedisCluster wraps Exception during discovery; the deadline must escape it.
    pass


@contextmanager
def deadline(seconds):
    """Bound an entire phase, including Redis discovery and socket handshakes."""
    def expired(signum, frame):
        raise PhaseTimeout(f"Timed out after {seconds:g}s")

    previous = signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, *previous_timer)
        signal.signal(signal.SIGALRM, previous)


def connection_options(timeout):
    return dict(decode_responses=True, socket_connect_timeout=min(timeout, 2),
                socket_timeout=min(timeout, 2), retry=Retry(NoBackoff(), 0),
                retry_on_error=[])


def node_client(port, timeout):
    return Redis(host=HOST, port=port, **connection_options(timeout))


def read_snapshots(base_port, timeout, health=False):
    snapshots = {}
    for port in range(base_port, base_port + 6):
        client = node_client(port, timeout)
        try:
            if client.ping() is not True:
                raise CheckError(f"{HOST}:{port}: PING failed")
            server = client.info("server")
            if server.get("server_name") != "valkey" or not server.get("valkey_version"):
                raise CheckError(f"{HOST}:{port}: endpoint is not a Valkey server")
            snapshot = {"server": server, "cluster": client.execute_command("CLUSTER INFO")}
            if health:
                # Separate command arguments preserve the raw CLUSTER NODES text.
                snapshot["nodes"] = client.execute_command("CLUSTER", "NODES")
                snapshot["replication"] = client.info("replication")
            else:
                snapshot["dbsize"] = client.dbsize()
            snapshots[port] = snapshot
        finally:
            client.close()
    return snapshots


def classify_state(snapshots):
    if len(snapshots) != 6:
        raise CheckError("Cannot classify state without all six nodes")
    for snapshot in snapshots.values():
        info = snapshot["cluster"]
        if (int(info["cluster_known_nodes"]) != 1
                or int(info["cluster_slots_assigned"]) != 0
                or snapshot["dbsize"] != 0):
            return "existing"
    return "fresh"


def parse_topology(text, base_port, observed_port):
    nodes, endpoints, observers = {}, set(), []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 8:
            raise CheckError("Malformed CLUSTER NODES row")
        node_id, endpoint, flags_text, master_id, _, _, _, link = fields[:8]
        flags = set(flags_text.split(","))
        if (not NODE_ID.fullmatch(node_id) or node_id in nodes or link != "connected"
                or flags - {"myself", "master", "slave"}
                or len(flags & {"master", "slave"}) != 1):
            raise CheckError("Unhealthy or malformed cluster node")
        address, _, _ = endpoint.partition(",")
        match = re.fullmatch(r"127\.0\.0\.1:(\d+)@(\d+)", address)
        if match is None:
            raise CheckError(f"Unexpected node endpoint: {endpoint}")
        port, bus_port = map(int, match.groups())
        if port in endpoints or port not in range(base_port, base_port + 6) or bus_port != port + 10000:
            raise CheckError(f"Unexpected or duplicate node endpoint: {endpoint}")
        endpoints.add(port)
        if "myself" in flags:
            observers.append(port)
        ranges = []
        for slot in fields[8:]:
            if not re.fullmatch(r"\d+(?:-\d+)?", slot):
                raise CheckError(f"Invalid or migrating slot: {slot}")
            start, _, end = slot.partition("-")
            start, end = int(start), int(end or start)
            if not 0 <= start <= end < 16384:
                raise CheckError(f"Invalid slot range: {slot}")
            ranges.append((start, end))
        role = "master" if "master" in flags else "slave"
        if role == "master" and (master_id != "-" or not ranges):
            raise CheckError("Primary is missing slots or has an upstream")
        if role == "slave" and (not NODE_ID.fullmatch(master_id) or ranges):
            raise CheckError("Replica has invalid upstream or owns slots")
        nodes[node_id] = (port, role, master_id, tuple(sorted(ranges)))
    if endpoints != set(range(base_port, base_port + 6)) or observers != [observed_port]:
        raise CheckError("Topology does not contain exactly the six expected nodes and observer")
    return nodes


def validate_health(snapshots, base_port):
    if set(snapshots) != set(range(base_port, base_port + 6)):
        raise CheckError("Health requires all six direct node endpoints")
    agreed = None
    for port, snapshot in snapshots.items():
        info = snapshot["cluster"]
        expected = {"cluster_slots_ok": 16384, "cluster_slots_assigned": 16384,
                    "cluster_known_nodes": 6, "cluster_size": 3,
                    "cluster_slots_fail": 0, "cluster_slots_pfail": 0}
        if info.get("cluster_state") != "ok" or any(
                int(info.get(field, -1)) != value for field, value in expected.items()):
            raise CheckError(f"{HOST}:{port}: cluster is not healthy")
        nodes = parse_topology(snapshot["nodes"], base_port, port)
        if agreed is not None and nodes != agreed:
            raise CheckError(f"{HOST}:{port}: topology disagrees with other nodes")
        agreed = nodes
        own_node = next(node for node in nodes.values() if node[0] == port)
        replication = snapshot["replication"]
        if replication.get("role") != own_node[1]:
            raise CheckError(f"{HOST}:{port}: replication role disagrees with topology")
        if own_node[1] == "slave":
            upstream = nodes.get(own_node[2])
            if (upstream is None or upstream[1] != "master"
                    or replication.get("master_link_status") != "up"
                    or replication.get("master_host") != HOST
                    or int(replication.get("master_port", -1)) != upstream[0]
                    or int(replication.get("master_sync_in_progress", -1)) != 0):
                raise CheckError(f"{HOST}:{port}: replica is not synchronized with its primary")
        elif int(replication.get("connected_slaves", -1)) != 1:
            raise CheckError(f"{HOST}:{port}: primary must have one online replica")
    primaries = {node_id: node[3] for node_id, node in agreed.items() if node[1] == "master"}
    if len(primaries) != 3 or any(
            sum(node[1] == "slave" and node[2] == primary for node in agreed.values()) != 1
            for primary in primaries):
        raise CheckError("Expected three primaries with exactly one replica each")
    cursor = 0
    for start, end in sorted(interval for ranges in primaries.values() for interval in ranges):
        if start != cursor:
            raise CheckError("Primary slots have gaps or overlap")
        cursor = end + 1
    if cursor != 16384:
        raise CheckError("Primary slots do not cover all 16384 slots")
    return primaries


def wait_for(check, timeout):
    last_error = None
    try:
        with deadline(timeout):
            while True:
                try:
                    return check()
                except (RedisError, CheckError, OSError) as exc:
                    last_error = exc
                    time.sleep(min(0.2, timeout))
    except PhaseTimeout as exc:
        raise CheckError(f"{exc}; last error: {last_error or 'host endpoint did not respond'}") from None


def smoke(base_port, timeout, primaries):
    client = None
    written = []
    try:
        with deadline(timeout):
            client = RedisCluster(host=HOST, port=base_port, require_full_coverage=True,
                                  **connection_options(timeout))
            remaining = dict(primaries)
            prefix = f"valkey-smoke:{uuid.uuid4().hex}:"
            counter = 0
            while remaining:
                key = f"{prefix}{counter}"
                counter += 1
                slot = key_slot(key.encode())
                owner = next((node_id for node_id, ranges in remaining.items()
                              if any(start <= slot <= end for start, end in ranges)), None)
                if owner is None:
                    continue
                value = f"roundtrip:{key}"
                # NX protects existing data even in the event of a UUID collision.
                if client.set(key, value, ex=60, nx=True) is not True:
                    raise CheckError(f"SET failed for smoke key {key}")
                written.append(key)
                got = client.get(key)
                if got != value:
                    raise CheckError(f"Readback mismatch for {key}: {got!r}")
                print(f"Primary {owner}: slot {slot} read/write OK")
                del remaining[owner]
    finally:
        if client is not None:
            try:
                # Cleanup is a separately bounded phase; TTL also covers process death.
                with deadline(timeout):
                    for key in written:
                        client.delete(key)
            finally:
                client.close()


def ports_free(ports):
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            try:
                connection.bind((HOST, port))
            except OSError as exc:
                raise CheckError(f"{HOST}:{port} is not available: {exc}") from None


def positive_timeout(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return seconds


def port_number(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-port", type=port_number,
                        default=os.environ.get("VALKEY_BASE_PORT", "7100"))
    parser.add_argument("--timeout", type=positive_timeout, default=60,
                        help="deadline in seconds for each phase (default: 60)")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--wait-nodes", action="store_true")
    modes.add_argument("--state", action="store_true")
    modes.add_argument("--health", action="store_true")
    modes.add_argument("--ports-free", type=port_number, nargs="+", metavar="PORT")
    modes.add_argument("--node-id", type=port_number, metavar="PORT")
    args = parser.parse_args(argv)
    if not args.ports_free and not args.node_id and args.base_port > 55530:
        parser.error("base port must leave room for six client and bus ports (maximum 55530)")
    try:
        if args.ports_free:
            with deadline(args.timeout):
                ports_free(args.ports_free)
        elif args.node_id:
            with deadline(args.timeout):
                client = node_client(args.node_id, args.timeout)
                try:
                    node_id = client.execute_command("CLUSTER", "MYID")
                    if not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id):
                        raise CheckError("CLUSTER MYID returned an invalid node ID")
                    print(node_id)
                finally:
                    client.close()
        elif args.state:
            with deadline(args.timeout):
                print(classify_state(read_snapshots(args.base_port, args.timeout)))
        elif args.wait_nodes:
            wait_for(lambda: read_snapshots(args.base_port, args.timeout), args.timeout)
        else:
            def healthy():
                snapshots = read_snapshots(args.base_port, args.timeout, health=True)
                return snapshots, validate_health(snapshots, args.base_port)
            snapshots, primaries = wait_for(healthy, args.timeout)
            for port, snapshot in snapshots.items():
                print(f"{HOST}:{port}: Valkey {snapshot['server']['valkey_version']}")
            if not args.health:
                smoke(args.base_port, args.timeout, primaries)
        return 0
    except (RedisError, RedisClusterException, CheckError, PhaseTimeout, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Cluster check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
