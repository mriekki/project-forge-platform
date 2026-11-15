"""Package-owned acceptance tests for the exact *assembled* Deployment Kit.

Release preparation runs this file against assets/generated/deployment/src,
not a local consumer tree or a pip-installed package. No Docker command,
real backup deletion, provider call or Production resource is used.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from project_forge_deployment import auth_recovery_lifecycle as lifecycle
from project_forge_deployment import auth_recovery_retention as retention
from project_forge_deployment.errors import DeploymentKitError


@unittest.skipUnless(sys.platform == "linux", "disposable recovery requires Linux")
class PackagedDisposableAuthRecoverySafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fail closed if a global/older pip installation was imported instead
        # of the exact generated package payload under verification.
        env = os.environ.get("PROJECT_FORGE_PACKAGED_DEPLOYMENT_ROOT")
        if not env:
            raise AssertionError("Exact assembled Deployment package root is required")
        root = Path(env).resolve(strict=True)
        for module in (lifecycle, retention):
            origin = Path(module.__file__).resolve(strict=True)
            if not origin.is_relative_to(root):
                raise AssertionError(
                    "Test imported Deployment outside exact assembled package"
                )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pf-packaged-auth-safety-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.dirs = {}
        for name in ("project", "source", "backups", "status", "lock"):
            directory = self.root / name
            directory.mkdir(mode=0o700)
            self.dirs[name] = directory
        source = self.dirs["source"]
        self.binding = {
            "container_name": "pf-disposable-synthetic",
            "expected_owner": "synthetic/project",
            "expected_environment": "disposable",
            "expected_image_digest": "sha256:" + "a" * 64,
            "expected_data_source": source,
            "expected_data_destination": "/app/data",
            "owner_label": "project-forge.owner",
            "environment_label": "project-forge.environment",
            "required_auth_environment": {
                "ProjectForge__Authentication__DbPath": "/app/data/auth.sqlite",
                "ProjectForge__Authentication__DataProtectionKeysPath": "/app/data/keys",
            },
        }
        self.proof = {
            "stopped": True,
            "runtimeId": "b" * 64,
            "imageDigest": self.binding["expected_image_digest"],
        }
        self.snapshot = {
            "Id": "b" * 64, "Name": "/pf-disposable-synthetic",
            "Image": self.binding["expected_image_digest"],
            "State": {"Running": True, "Restarting": False, "Status": "running"},
            "Config": {
                "Labels": {
                    "project-forge.owner": "synthetic/project",
                    "project-forge.environment": "disposable",
                },
                "Env": [
                    "ProjectForge__Authentication__DbPath=/app/data/auth.sqlite",
                    "ProjectForge__Authentication__DataProtectionKeysPath=/app/data/keys",
                ],
            },
            "HostConfig": {"RestartPolicy": {"Name": "no"}},
            "Mounts": [{"Type": "bind", "Source": str(source),
                        "Destination": "/app/data", "RW": True}],
        }
        self.last = {"setName": "20261114T120000Z-cccccccc",
                     "completedAt": "2026-11-14T12:00:00Z"}
        self.candidate = "20261112T120000Z-aaaaaaaa"
        self.preview = {
            "retentionPlanOnly": True,
            "deletionPerformed": False,
            "verifiedRecoverySetNames": [
                self.candidate, "20261113T120000Z-bbbbbbbb",
                self.last["setName"],
            ],
            "retainedRecoverySetNames": [
                "20261113T120000Z-bbbbbbbb", self.last["setName"],
            ],
            "retentionCandidateNames": [self.candidate],
        }
        self.plan_helper = Mock(return_value=copy.deepcopy(self.preview))
        self.delete_helper = Mock(return_value={
            "deletedRecoverySetNames": [self.candidate],
            "deletionPerformed": True,
        })
        self.helper = types.SimpleNamespace(
            plan_verified_retention=self.plan_helper,
            apply_reviewed_disposable_retention=self.delete_helper,
        )
        self.config = {
            "project": self.dirs["project"],
            "backups": self.dirs["backups"],
            "lock": self.dirs["lock"],
            "status": self.dirs["status"],
            "declaration": {"schemaVersion": 1, "projectId": "synthetic-project"},
            "revision": "d" * 40, "helperSha": "e" * 64,
            "binding": self.binding,
        }

    def _recover(self):
        with patch.object(lifecycle.sys, "platform", "linux"), patch.object(
            lifecycle.shutil, "which", return_value="/usr/bin/docker"
        ), patch.object(
            lifecycle, "_docker_inspect",
            return_value=copy.deepcopy(self.snapshot)
        ), patch.object(lifecycle, "_docker_action") as action:
            result = lifecycle.recover_interrupted_disposable_auth(
                lock_directory=self.dirs["lock"],
                reviewed_docker_binding=self.binding,
                authorize_disposable_resume=True,
            )
            return result, action

    def _plan(self):
        with patch.object(retention, "_verified_backup", return_value=self.last), patch.object(
            retention, "_verified_helper", return_value=self.helper
        ):
            return retention.create_reviewed_disposable_retention_plan(
                self.config, keep_last=2
            )

    def _apply(self, digest):
        with patch.object(retention, "_verified_backup", return_value=self.last), patch.object(
            retention, "_verified_helper", return_value=self.helper
        ):
            return retention.apply_reviewed_disposable_retention(
                self.config, expected_plan_sha256=digest,
                authorize_disposable_delete=True,
            )

    def test_interrupted_exact_container_already_running_is_not_started_again(self):
        lifecycle._create_restart_journal(
            self.dirs["lock"], self.binding, self.proof, self.last["setName"]
        )
        result, action = self._recover()
        action.assert_not_called()
        self.assertTrue(result["runtimeResumedVerified"])
        self.assertFalse(result["mutated"])
        self.assertFalse(result["applicationRecoveryReady"])
        self.assertFalse(result["normalTrafficReadinessProven"])
        self.assertFalse((self.dirs["lock"] / lifecycle.RESTART_JOURNAL).exists())

    def test_replacement_container_identity_is_refused_and_journal_survives(self):
        lifecycle._create_restart_journal(
            self.dirs["lock"], self.binding, self.proof, self.last["setName"]
        )
        self.snapshot["Id"] = "f" * 64
        self.snapshot["State"].update({"Running": False, "Status": "exited"})
        with patch.object(lifecycle.sys, "platform", "linux"), patch.object(
            lifecycle.shutil, "which", return_value="/usr/bin/docker"
        ), patch.object(
            lifecycle, "_docker_inspect", return_value=copy.deepcopy(self.snapshot)
        ), patch.object(lifecycle, "_docker_action") as action:
            with self.assertRaisesRegex(DeploymentKitError, "original Docker ID changed"):
                lifecycle.recover_interrupted_disposable_auth(
                    lock_directory=self.dirs["lock"],
                    reviewed_docker_binding=self.binding,
                    authorize_disposable_resume=True,
                )
            action.assert_not_called()
        self.assertTrue((self.dirs["lock"] / lifecycle.RESTART_JOURNAL).is_file())

    def test_retention_inventory_drift_refuses_deletion_and_started_receipt(self):
        planned = self._plan()
        changed = copy.deepcopy(self.preview)
        changed["retainedRecoverySetNames"][0] = "20261113T120000Z-dddddddd"
        self.plan_helper.return_value = changed
        with self.assertRaisesRegex(DeploymentKitError, "inventory changed"):
            self._apply(planned["planSha256"])
        self.delete_helper.assert_not_called()
        self.assertFalse(list(self.dirs["status"].glob("auth-retention-*-started.json")))
        self.assertFalse(list(self.dirs["status"].glob("auth-retention-*-completed.json")))

    def test_partial_deletion_has_private_failure_not_completion_receipt(self):
        planned = self._plan()
        self.delete_helper.return_value = {
            "deletedRecoverySetNames": [], "deletionPerformed": True
        }
        with self.assertRaisesRegex(DeploymentKitError, "incomplete"):
            self._apply(planned["planSha256"])
        started = list(self.dirs["status"].glob("auth-retention-*-started.json"))
        failed = list(self.dirs["status"].glob("auth-retention-*-failed.json"))
        completed = list(self.dirs["status"].glob("auth-retention-*-completed.json"))
        self.assertEqual((len(started), len(failed), len(completed)), (1, 1, 0))
        record = json.loads(failed[0].read_text())
        self.assertEqual(record["outcome"], "failed-or-unverified")
        self.assertEqual(failed[0].stat().st_mode & 0o077, 0)

    def test_interrupted_deletion_leaves_start_only_and_never_claims_success(self):
        planned = self._plan()
        self.delete_helper.side_effect = KeyboardInterrupt("synthetic interruption")
        with self.assertRaises(KeyboardInterrupt):
            self._apply(planned["planSha256"])
        self.assertEqual(len(list(self.dirs["status"].glob("auth-retention-*-started.json"))), 1)
        self.assertFalse(list(self.dirs["status"].glob("auth-retention-*-failed.json")))
        self.assertFalse(list(self.dirs["status"].glob("auth-retention-*-completed.json")))


if __name__ == "__main__":
    unittest.main()
