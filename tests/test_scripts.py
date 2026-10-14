"""Script failure and data-safety regressions; no real Docker daemon is used."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScriptSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="valkey-scripts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        for name in ("init.sh", "start.sh", "stop.sh", "test.sh", "lib.sh", ".env", "docker-compose.yml"):
            shutil.copy2(ROOT / name, self.project / name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("VALKEY_", "COMPOSE_"))}
        self.env.update(PATH=f"{self.bin}:{os.environ['PATH']}", TEST_WAIT_TIME="0",
                        TMPDIR=str(self.root))

    def docker(self, body):
        path = self.bin / "docker"
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)

    def run_script(self, name, *args):
        return subprocess.run(["/bin/bash", str(self.project / name), *args],
                              cwd=self.project, env=self.env, text=True,
                              capture_output=True, timeout=15)

    def test_start_propagates_docker_failure(self):
        self.docker("exit 42\n")
        result = self.run_script("start.sh")
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_stop_propagates_docker_failure(self):
        self.docker("exit 42\n")
        result = self.run_script("stop.sh")
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_failed_deployment_never_deletes_user_data(self):
        self.docker('if [[ " $* " == *" down "* ]]; then exit 42; fi\nexit 0\n')
        (self.project / "init.sh").write_text("#!/bin/bash\nexit 1\n")
        (self.project / "init.sh").chmod(0o755)
        data = self.project / "data"
        data.mkdir()
        sentinel = data / "existing-data"
        sentinel.write_text("must survive failed test cleanup")
        self.env["VALKEY_DATA_DIR"] = str(data)
        result = self.run_script("test.sh", "7.2.14-alpine")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue(sentinel.exists(), "test.sh deleted existing project data")
        self.assertEqual(sentinel.read_text(), "must survive failed test cleanup")

    def test_cleanup_failure_retains_temporary_data(self):
        self.docker('if [[ " $* " == *" down "* ]]; then exit 42; fi\nexit 0\n')
        (self.project / "init.sh").write_text(
            '#!/bin/bash\nmkdir -p "$VALKEY_DATA_DIR"\n'
            'printf diagnostic > "$VALKEY_DATA_DIR/retain-me"\nexit 1\n')
        result = self.run_script("test.sh", "7.2.14-alpine")
        self.assertNotEqual(result.returncode, 0)
        retained = list(self.root.glob("valkey-test.*/0/retain-me"))
        self.assertEqual(len(retained), 1, result.stdout + result.stderr)
        self.assertEqual(retained[0].read_text(), "diagnostic")

    def test_changed_image_cannot_reuse_persistent_data(self):
        self.docker("exit 0\n")
        python = self.bin / "python-check"
        python.write_text("#!/bin/bash\nexit 0\n")
        python.chmod(0o755)
        self.env["PYTHON"] = str(python)
        data = self.root / "persistent"
        data.mkdir()
        (data / "nodes.conf").write_text("existing cluster state")
        marker = data / ".cluster-settings"
        original = "valkey/valkey:7.2.14-alpine 7100\n"
        marker.write_text(original)
        self.env.update(VALKEY_DATA_DIR=str(data), VALKEY_IMAGE="9.1.2-alpine")
        result = self.run_script("start.sh")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(marker.read_text(), original)

    def test_empty_failed_deployment_allows_corrected_image(self):
        self.docker('if [[ " $* " == *" up "* ]]; then exit 42; fi\nexit 0\n')
        python = self.bin / "python-check"
        python.write_text("#!/bin/bash\nexit 0\n")
        python.chmod(0o755)
        self.env["PYTHON"] = str(python)
        data = self.root / "empty-failed-deployment"
        (data / "node-0").mkdir(parents=True)
        marker = data / ".cluster-settings"
        marker.write_text("valkey/valkey:misspelled-tag 7100\n")
        self.env.update(VALKEY_DATA_DIR=str(data), VALKEY_IMAGE="7.2.14-alpine")
        result = self.run_script("start.sh")
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(marker.read_text(), "valkey/valkey:7.2.14-alpine 7100\n")


if __name__ == "__main__":
    unittest.main()
