"""Regression tests for the local-only Valkey helper (no Docker required)."""
import io
import socket
import sys
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redis_cluster_test as helper
from redis.exceptions import ConnectionError, RedisClusterException


BASE = 27100
IDS = [f"{index + 1:040x}" for index in range(6)]


def topology(observer=0):
    rows = []
    ranges = ["0-5460", "5461-10922", "10923-16383"]
    for index, node_id in enumerate(IDS):
        role = "master" if index < 3 else "slave"
        flags = f"myself,{role}" if index == observer else role
        upstream = "-" if index < 3 else IDS[index - 3]
        slots = f" {ranges[index]}" if index < 3 else ""
        rows.append(
            f"{node_id} 127.0.0.1:{BASE + index}@{BASE + index + 10000} "
            f"{flags} {upstream} 0 0 1 connected{slots}"
        )
    return "\n".join(rows)


def snapshots():
    result = {}
    for index in range(6):
        replica = index >= 3
        result[BASE + index] = {
            "server": {"server_name": "valkey", "valkey_version": "7.2.14"},
            "cluster": {"cluster_state": "ok", "cluster_slots_ok": 16384,
                        "cluster_slots_assigned": 16384, "cluster_known_nodes": 6,
                        "cluster_size": 3, "cluster_slots_fail": 0,
                        "cluster_slots_pfail": 0},
            "nodes": topology(index),
            "replication": ({"role": "slave", "master_link_status": "up",
                             "master_host": "127.0.0.1",
                             "master_port": BASE + index - 3,
                             "master_sync_in_progress": 0}
                            if replica else {"role": "master", "connected_slaves": 1}),
        }
    return result


class TopologyTests(unittest.TestCase):
    def test_all_six_agree_and_each_primary_has_one_replica(self):
        primaries = helper.validate_health(snapshots(), BASE)
        self.assertEqual(set(primaries), {IDS[0], IDS[1], IDS[2]})

    def test_rejects_unhealthy_direct_node_even_if_first_is_healthy(self):
        data = snapshots()
        data[BASE + 5]["cluster"]["cluster_state"] = "fail"
        with self.assertRaises(helper.CheckError):
            helper.validate_health(data, BASE)

    def test_rejects_replica_with_broken_replication_link(self):
        data = snapshots()
        data[BASE + 5]["replication"]["master_link_status"] = "down"
        with self.assertRaises(helper.CheckError):
            helper.validate_health(data, BASE)

    def test_rejects_topology_disagreement(self):
        data = snapshots()
        data[BASE + 5]["nodes"] = data[BASE + 5]["nodes"].replace(IDS[0], "f" * 40)
        with self.assertRaises(helper.CheckError):
            helper.validate_health(data, BASE)

    def test_rejects_malformed_or_incomplete_topology(self):
        replacements = [
            (" connected", " disconnected"),
            (" slave ", " slave,fail "),
            ("127.0.0.1", "192.0.2.1"),
            ("0-5460", "0-5459"),
            ("0-5460", "0-5461"),
            ("0-5460", "0-5460 [5461->-deadbeef]"),
            (f"@{BASE + 10000}", "@1"),
            (" connected", " connected bad-slot"),
            (f"slave {IDS[2]}", f"slave {IDS[0]}"),
        ]
        for old, new in replacements:
            with self.subTest(change=(old, new)):
                data = snapshots()
                for snapshot in data.values():
                    snapshot["nodes"] = snapshot["nodes"].replace(old, new)
                with self.assertRaises(helper.CheckError):
                    helper.validate_health(data, BASE)

    def test_missing_direct_node_is_not_healthy(self):
        data = snapshots()
        del data[BASE + 5]
        with self.assertRaises(helper.CheckError):
            helper.validate_health(data, BASE)


class StateTests(unittest.TestCase):
    def fresh(self):
        return {BASE + index: {"cluster": {"cluster_known_nodes": 1,
                "cluster_slots_assigned": 0}, "dbsize": 0} for index in range(6)}

    def test_only_all_six_empty_unjoined_nodes_are_fresh(self):
        self.assertEqual(helper.classify_state(self.fresh()), "fresh")

    def test_partial_cluster_or_data_is_existing(self):
        for section, field, value in [("cluster", "cluster_known_nodes", 2),
                                      ("cluster", "cluster_slots_assigned", 1),
                                      (None, "dbsize", 1)]:
            with self.subTest(field=field):
                data = self.fresh()
                target = data[BASE + 5] if section is None else data[BASE + 5][section]
                target[field] = value
                self.assertEqual(helper.classify_state(data), "existing")

    def test_inaccessible_node_is_failure_not_existing(self):
        with patch.object(helper, "read_snapshots", side_effect=ConnectionError("unreachable")):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(helper.main(["--state", "--timeout", "0.1"]), 1)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("unreachable", err.getvalue())


class MemoryCluster:
    def __init__(self, wrong=False):
        self.values = {}
        self.writes = []
        self.deleted = []
        self.wrong = wrong
        self.closed = False

    def set(self, key, value, ex, nx):
        if key in self.values:
            return False
        self.values[key] = value
        self.writes.append((key, ex, nx))
        return True

    def get(self, key):
        return "wrong value" if self.wrong else self.values[key]

    def delete(self, key):
        self.deleted.append(key)
        return int(self.values.pop(key, None) is not None)

    def close(self):
        self.closed = True


class SmokeTests(unittest.TestCase):
    def run_smoke(self, cluster):
        with patch.object(helper, "RedisCluster", return_value=cluster):
            helper.smoke(BASE, 1, helper.validate_health(snapshots(), BASE))

    def test_roundtrips_one_key_owned_by_each_primary_and_cleans_up(self):
        cluster = MemoryCluster()
        self.run_smoke(cluster)
        owners = helper.validate_health(snapshots(), BASE)
        written_slots = [helper.key_slot(key.encode()) for key, _, _ in cluster.writes]
        self.assertEqual(len(written_slots), 3)
        for ranges in owners.values():
            self.assertTrue(any(any(start <= slot <= end for start, end in ranges)
                                for slot in written_slots))
        self.assertTrue(all(ex == 60 and nx is True for _, ex, nx in cluster.writes))
        self.assertEqual(len(cluster.deleted), 3)
        self.assertEqual(cluster.values, {})
        self.assertTrue(cluster.closed)

    def test_wrong_readback_fails_and_still_deletes_keys(self):
        cluster = MemoryCluster(wrong=True)
        with self.assertRaises(helper.CheckError):
            self.run_smoke(cluster)
        self.assertEqual(cluster.values, {})
        self.assertTrue(cluster.closed)

    def test_connection_failure_propagates(self):
        with patch.object(helper, "RedisCluster", side_effect=ConnectionError("no route")):
            with self.assertRaises(ConnectionError):
                helper.smoke(BASE, 1, helper.validate_health(snapshots(), BASE))

    def test_each_run_uses_unique_keys(self):
        first, second = MemoryCluster(), MemoryCluster()
        self.run_smoke(first)
        self.run_smoke(second)
        self.assertTrue({row[0] for row in first.writes}.isdisjoint(
                        {row[0] for row in second.writes}))


class CliTests(unittest.TestCase):
    def invoke(self, arguments):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = helper.main(arguments)
        return status, out.getvalue(), err.getvalue()

    def test_occupied_ipv4_port_is_failure(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            status, _, error = self.invoke(["--ports-free", str(port)])
        self.assertEqual(status, 1)
        self.assertIn(f"127.0.0.1:{port}", error)

    def test_hung_host_is_bounded_and_does_not_fall_back(self):
        release = threading.Event()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            def hang():
                with listener.accept()[0]:
                    release.wait(2)
            worker = threading.Thread(target=hang, daemon=True)
            worker.start()
            try:
                started = time.monotonic()
                status, _, _ = self.invoke(["--node-id", str(port), "--timeout", "0.1"])
                self.assertEqual(status, 1)
                self.assertLess(time.monotonic() - started, 1)
            finally:
                release.set()
                worker.join(2)

    def test_node_identity_stdout_is_only_id_and_connection_is_closed(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.execute_command.return_value = IDS[0]
        with patch.object(helper, "node_client", return_value=connection):
            status, out, err = self.invoke(["--node-id", str(BASE)])
        self.assertEqual((status, out, err), (0, IDS[0] + "\n", ""))
        connection.close.assert_called_once()

    def test_wrong_server_is_failure(self):
        from unittest.mock import MagicMock
        connection = MagicMock()
        connection.ping.return_value = True
        connection.info.return_value = {"server_name": "redis", "redis_version": "7.2.0"}
        with patch.object(helper, "node_client", return_value=connection):
            status, _, _ = self.invoke(["--wait-nodes", "--timeout", "0.02"])
        self.assertEqual(status, 1)

    def test_health_cli_failure_has_nonzero_status(self):
        with patch.object(helper, "read_snapshots", side_effect=ConnectionError("unreachable")):
            status, _, _ = self.invoke(["--health", "--timeout", "0.02"])
        self.assertEqual(status, 1)

    def test_wrong_smoke_readback_has_nonzero_exit_status(self):
        cluster = MemoryCluster(wrong=True)
        with patch.object(helper, "read_snapshots", return_value=snapshots()), \
                patch.object(helper, "RedisCluster", return_value=cluster):
            status, _, err = self.invoke(["--base-port", str(BASE), "--timeout", "1"])
        self.assertEqual(status, 1)
        self.assertIn("Readback mismatch", err)
        self.assertTrue(cluster.closed)

    def test_discovery_failure_after_health_has_controlled_exit(self):
        with patch.object(helper, "read_snapshots", return_value=snapshots()), \
                patch.object(helper, "RedisCluster", side_effect=RedisClusterException("unreachable")):
            status, _, _ = self.invoke(["--base-port", str(BASE)])
        self.assertEqual(status, 1)

    def test_state_stdout_is_only_classification(self):
        data = StateTests().fresh()
        with patch.object(helper, "read_snapshots", return_value=data):
            self.assertEqual(self.invoke(["--state"]), (0, "fresh\n", ""))

    def test_timeout_requires_positive_finite_value(self):
        for value in ["0", "-1", "nan", "inf"]:
            with self.subTest(value=value), self.assertRaises(SystemExit):
                self.invoke(["--timeout", value])


if __name__ == "__main__":
    unittest.main()
