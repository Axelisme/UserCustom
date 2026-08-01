from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any

from tests import _setup_support as setup_support
from tests._orchestrate_cli_support import (
    OrchestrateCliRepositoryTestCase,
    VERIFIED_SKILL,
    json_object,
    release,
)

ROOT = Path(__file__).resolve().parents[1]
CODEX_SKILL = ROOT / "home/.codex/skills/orchestrate"
PI_SKILL = ROOT / "home/.pi/agent/skills/orchestrate"
# Derived from the source package so a release does not require editing this file.
CURRENT_VERSION = release.skill_version(CODEX_SKILL)


class PackageCommandContractTests(OrchestrateCliRepositoryTestCase):
    """Contract module E through copied packages and the shipped subprocess."""

    def setUp(self) -> None:
        super().setUp()
        self.package_temporary = tempfile.TemporaryDirectory(
            prefix="orchestrate-v137-package-"
        )
        self.activate_package("primary")

    def tearDown(self) -> None:
        self.package_temporary.cleanup()
        super().tearDown()

    def activate_package(self, name: str) -> None:
        """Select a fresh disposable logical HOME without installing it."""
        home = Path(self.package_temporary.name) / name / "home"
        shutil.copytree(VERIFIED_SKILL.parents[2], home, symlinks=True)
        self.skill = home / ".codex" / "skills" / "orchestrate"
        self.script = self.skill / "scripts" / "orchestrate.py"

    def cli(self, cwd: Path, *argv: str, **unused: object):
        return super().cli(
            cwd,
            *argv,
            script=self.script,
            skill_dir=self.skill,
        )

    def current(self) -> int:
        match = re.search(
            rb"(?m)^skill_version: (\d+)$",
            (self.skill / "SKILL.md").read_bytes(),
        )
        if match is None:
            raise AssertionError("copied SKILL.md has no exact skill_version")
        return int(match.group(1))

    def seal_current_package(self) -> dict[str, Any]:
        """Fixture helper: seal copied bytes before crossing the public seam."""
        version = self.current()
        manifest = release.build_manifest(self.skill, version)
        (self.skill / "manifests" / f"{version}.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest

    def package_projection(self) -> dict[str, int]:
        manifest = json.loads(
            (self.skill / "manifests" / f"{self.current()}.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            "current": self.current(),
            "documents": len(manifest["documents"]),
            "profiles": len(manifest["profiles"]),
            "runtime_assets": 0,
        }

    def pin_path(self) -> Path:
        return self.root / ".agent_state" / "orchestrate" / "version-pin.json"

    def assert_package_failure(
        self,
        result,
        operation: str,
        code: str,
    ) -> dict[str, Any]:
        payload = self.operational_failure(result, operation, code)
        self.assertNotIn("Traceback", result.stderr)
        return payload

    def test_01_help_and_pin_status_are_exact_and_cwd_derived(self) -> None:
        help_texts = [
            self.assert_help_surface(
                (),
                commands=(
                    "status",
                    "timing",
                    "lane",
                    "integration",
                    "acceptance",
                    "report",
                    "pin",
                    "doctor",
                    "release",
                ),
                long_options=("--skill-dir",),
            ),
            self.assert_help_surface(("pin",), commands=("status", "set")),
            self.assert_help_surface(("pin", "status")),
            self.assert_help_surface(("pin", "set")),
            self.assert_help_surface(
                ("doctor",), commands=("diff",), long_options=("--path",)
            ),
            self.assert_help_surface(
                ("doctor", "diff"), long_options=("--runtime",)
            ),
            self.assert_help_surface(("release",), long_options=("--version",)),
        ]
        all_help = "\n".join(help_texts)
        for retired in (
            "--root",
            "--previous-version",
            "--output",
            "--compat",
        ):
            self.assertNotIn(retired, all_help)
        root_commands = re.search(r"\{([^{}]+)\}", help_texts[0])
        self.assertIsNotNone(root_commands)
        assert root_commands is not None
        self.assertNotIn("diff", root_commands.group(1).split(","))

        self.assertEqual(
            self.success(self.cli(self.nested, "pin", "status")),
            {
                "ok": True,
                "operation": "pin-status",
                "orchestrate_version": CURRENT_VERSION,
                "current": self.current(),
                "aligned": False,
            },
        )
        self.assertFalse(self.pin_path().exists())

        before = self.managed_state_snapshot()
        self.assert_package_failure(
            self.cli(self.nested, "pin", "status", "--root", str(self.root)),
            "cli",
            "cli_usage",
        )
        self.assertEqual(self.managed_state_snapshot(), before)

    def test_02_pin_set_verifies_current_and_aligned_set_preserves_bytes(self) -> None:
        self.mutation_success(self.cli(self.nested, "pin", "set"), "pin-set")
        pin_bytes = self.pin_path().read_bytes()
        pin = json.loads(pin_bytes)
        self.assertEqual(
            set(pin),
            {
                "pin_version",
                "skill_version",
                "orchestrate_compat",
                "pinned_at",
            },
        )
        self.assertEqual(pin["pin_version"], 1)
        self.assertEqual(pin["skill_version"], self.current())
        self.assertEqual(pin["orchestrate_compat"], self.current())
        self.assertIsInstance(pin["pinned_at"], str)
        self.assertTrue(pin["pinned_at"])
        self.assertEqual(
            self.success(self.cli(self.nested, "pin", "status")),
            {
                "ok": True,
                "operation": "pin-status",
                "orchestrate_version": CURRENT_VERSION,
                "current": self.current(),
                "pinned": self.current(),
                "aligned": True,
            },
        )

        aligned = self.mutation_success(
            self.cli(self.nested, "pin", "set"),
            "pin-set",
            warnings=True,
        )
        self.assertEqual(
            set(aligned),
            {"ok", "operation", "orchestrate_version", "warnings"},
        )
        self.assertEqual(self.pin_path().read_bytes(), pin_bytes)

        # Independently exercises corrupt-package mutation preflight: an aligned
        # pin must not bypass doctor and must not rewrite its timestamp bytes.
        runtime = self.skill / "runtime-codex.md"
        runtime.write_bytes(runtime.read_bytes() + b"\ncorrupt copied package\n")
        before = self.managed_state_snapshot()
        self.assert_package_failure(
            self.cli(self.nested, "pin", "set"),
            "pin-set",
            "package_unhealthy",
        )
        self.assertEqual(self.managed_state_snapshot(), before)
        self.assertEqual(self.pin_path().read_bytes(), pin_bytes)

    def test_03_doctor_package_truth_is_independent_of_pin_projection(self) -> None:
        self.mutation_success(self.cli(self.nested, "pin", "set"), "pin-set")
        pin = json.loads(self.pin_path().read_text(encoding="utf-8"))
        pin["skill_version"] = self.current() - 1
        self.pin_path().write_text(
            json.dumps(pin, sort_keys=True), encoding="utf-8"
        )
        expected_package = self.package_projection()

        unaligned = self.success(self.cli(self.nested, "doctor"))
        self.assertEqual(
            set(unaligned),
            {
                "ok",
                "operation",
                "orchestrate_version",
                "package",
                "repository",
                "warnings",
            },
        )
        self.assertEqual(unaligned["operation"], "doctor")
        self.assertEqual(unaligned["orchestrate_version"], CURRENT_VERSION)
        self.assertEqual(unaligned["package"], expected_package)
        self.assertEqual(
            unaligned["repository"],
            {"pinned": self.current() - 1, "aligned": False},
        )
        self.assertTrue(unaligned["warnings"])

        with tempfile.TemporaryDirectory(prefix="orchestrate-no-repo-") as outside:
            no_repository = self.success(self.cli(Path(outside), "doctor"))
            self.assertEqual(
                set(no_repository),
                {
                    "ok",
                    "operation",
                    "orchestrate_version",
                    "package",
                    "warnings",
                },
            )
            self.assertEqual(no_repository["package"], expected_package)
            self.assertTrue(no_repository["warnings"])

            explicit = self.success(
                self.cli(Path(outside), "doctor", "--path", str(self.nested))
            )
            self.assertEqual(explicit["package"], expected_package)
            self.assertEqual(explicit["repository"], unaligned["repository"])
            self.assertTrue(explicit["warnings"])

        self.pin_path().unlink()
        missing = self.success(self.cli(self.nested, "doctor"))
        self.assertNotIn("repository", missing)
        self.assertEqual(missing["package"], expected_package)
        self.assertTrue(missing["warnings"])

    def test_04_doctor_predicate_failure_is_structured_and_still_projects_pin(
        self,
    ) -> None:
        self.mutation_success(self.cli(self.nested, "pin", "set"), "pin-set")
        pin = json.loads(self.pin_path().read_text(encoding="utf-8"))
        pin["skill_version"] = self.current() - 1
        self.pin_path().write_text(
            json.dumps(pin, sort_keys=True), encoding="utf-8"
        )
        runtime = self.skill / "runtime-claude.md"
        runtime.write_bytes(runtime.read_bytes() + b"\npackage drift\n")

        result = self.cli(self.nested, "doctor")

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("Traceback", result.stdout)
        payload = json_object(result.stdout)
        self.assertEqual(
            set(payload),
            {
                "ok",
                "operation",
                "orchestrate_version",
                "package",
                "repository",
                "warnings",
                "diagnostics",
            },
        )
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["operation"], "doctor")
        self.assertEqual(payload["orchestrate_version"], CURRENT_VERSION)
        self.assertEqual(payload["package"], self.package_projection())
        self.assertEqual(
            payload["repository"],
            {"pinned": self.current() - 1, "aligned": False},
        )
        self.assertTrue(payload["warnings"])
        diagnostics = payload["diagnostics"]
        self.assertIsInstance(diagnostics, list)
        self.assertGreater(len(diagnostics), 0)
        self.assertLessEqual(len(diagnostics), 20)
        serialized = [json.dumps(item, sort_keys=True) for item in diagnostics]
        self.assertEqual(len(serialized), len(set(serialized)))
        for diagnostic in diagnostics:
            self.assertEqual(set(diagnostic), {"code", "message"})
            self.assertEqual(diagnostic["code"], "manifest_invalid")
            self.assertIsInstance(diagnostic["message"], str)
            self.assertTrue(diagnostic["message"])

    def test_05_doctor_diff_is_nested_immutable_sorted_and_runtime_filtered(
        self,
    ) -> None:
        old = self.current() - 1
        new = self.current()
        result = self.success(
            self.cli(self.nested, "doctor", "diff", str(old), str(new))
        )
        self.assertEqual(
            set(result),
            {
                "ok",
                "operation",
                "orchestrate_version",
                "from",
                "to",
                "compat",
                "changed_documents",
                "changed_profiles",
                "changed_runtime_assets",
                "must_reread",
                "acknowledge_removed",
            },
        )
        self.assertEqual(result["operation"], "doctor-diff")
        self.assertEqual(result["orchestrate_version"], CURRENT_VERSION)
        self.assertEqual((result["from"], result["to"]), (old, new))
        self.assertEqual(result["compat"], [old, new])
        document_paths = [item["path"] for item in result["changed_documents"]]
        self.assertEqual(document_paths, sorted(document_paths))
        for item in result["changed_documents"]:
            self.assertEqual(
                set(item),
                {
                    "path",
                    "change",
                    "changed_sections",
                    "must_reread",
                },
            )
            self.assertEqual(item["changed_sections"], sorted(item["changed_sections"]))
        for key in (
            "changed_profiles",
            "changed_runtime_assets",
            "must_reread",
            "acknowledge_removed",
        ):
            self.assertEqual(result[key], sorted(result[key]))

        # Comparison reads only the immutable bundled manifests, not live bytes.
        runtime_doc = self.skill / "runtime-codex.md"
        runtime_doc.write_bytes(runtime_doc.read_bytes() + b"\nlive drift\n")
        self.assertEqual(
            self.success(
                self.cli(self.nested, "doctor", "diff", str(old), str(new))
            ),
            result,
        )

        for runtime, prefix in (
            ("codex", ".codex/"),
            ("claude", ".claude/"),
            ("pi", ".pi/"),
        ):
            with self.subTest(runtime=runtime):
                filtered = self.success(
                    self.cli(
                        self.nested,
                        "doctor",
                        "diff",
                        str(old),
                        str(new),
                        "--runtime",
                        runtime,
                    )
                )
                self.assertEqual(
                    set(filtered), {*set(result), "runtime"}
                )
                self.assertEqual(filtered["runtime"], runtime)
                self.assertTrue(
                    all(
                        not item["path"].startswith("runtime-")
                        or item["path"] == f"runtime-{runtime}.md"
                        for item in filtered["changed_documents"]
                    )
                )
                self.assertTrue(
                    all(path.startswith(prefix) for path in filtered["changed_profiles"])
                )
                self.assertTrue(
                    all(
                        path.startswith(prefix)
                        for path in filtered["changed_runtime_assets"]
                    )
                )

        self.assert_package_failure(
            self.cli(self.nested, "diff", str(old), str(new)),
            "cli",
            "cli_usage",
        )
        self.assert_package_failure(
            self.cli(
                self.nested,
                "doctor",
                "diff",
                str(old),
                str(new),
                "--compat",
                "pi",
            ),
            "cli",
            "cli_usage",
        )

    def test_06_release_requires_explicit_exact_next_and_can_release_a_copy(
        self,
    ) -> None:
        current = self.current()
        skill_before = (self.skill / "SKILL.md").read_bytes()
        target_manifest = self.skill / "manifests" / f"{current + 1}.json"

        self.assert_package_failure(
            self.cli(self.nested, "release"), "cli", "cli_usage"
        )
        for target in (current, current - 1, current + 2):
            with self.subTest(target=target):
                self.assert_package_failure(
                    self.cli(
                        self.nested, "release", "--version", str(target)
                    ),
                    "release",
                    "invalid_release_target",
                )
                self.assertEqual(
                    (self.skill / "SKILL.md").read_bytes(), skill_before
                )
                self.assertFalse(target_manifest.exists())

        current_manifest = self.skill / "manifests" / f"{current}.json"
        manifest_bytes = current_manifest.read_bytes()
        current_manifest.unlink()
        self.assert_package_failure(
            self.cli(
                self.nested, "release", "--version", str(current + 1)
            ),
            "release",
            "package_unhealthy",
        )
        self.assertEqual((self.skill / "SKILL.md").read_bytes(), skill_before)
        self.assertFalse(target_manifest.exists())
        current_manifest.write_bytes(manifest_bytes)

        # A document the current manifest lists must still exist.
        binding = self.skill / "runtime-pi.md"
        binding_bytes = binding.read_bytes()
        binding.unlink()
        self.assert_package_failure(
            self.cli(
                self.nested, "release", "--version", str(current + 1)
            ),
            "release",
            "package_unhealthy",
        )
        self.assertEqual((self.skill / "SKILL.md").read_bytes(), skill_before)
        self.assertFalse(target_manifest.exists())
        binding.write_bytes(binding_bytes)

        guide = self.skill / "migrations" / f"{current + 1}.md"
        guide.write_text("# Disposable next release\n", encoding="utf-8")
        # No reseal: publication must proceed from a package whose bytes have
        # already moved past the current manifest, which is every real release.
        result = self.cli(
            self.nested, "release", "--version", str(current + 1)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        released = json_object(result.stdout)
        self.assertEqual(
            released,
            {
                "ok": True,
                "operation": "release",
                "orchestrate_version": current + 1,
            },
        )
        self.assertEqual(self.current(), current + 1)
        self.assertTrue(target_manifest.is_file())
        cli_source = self.skill / "scripts" / "_orchestrate" / "cli.py"
        manifest = json.loads(target_manifest.read_text(encoding="utf-8"))
        cli_entry = manifest["documents"]["scripts/_orchestrate/cli.py"]
        self.assertEqual(
            cli_entry["sha256"],
            hashlib.sha256(cli_source.read_bytes()).hexdigest(),
        )
        self.assertIn(
            f"ORCHESTRATE_VERSION = {current + 1}".encode(),
            cli_source.read_bytes(),
        )
        doctor = self.success(self.cli(self.nested, "doctor"))
        self.assertEqual(doctor["orchestrate_version"], current + 1)
        self.assertEqual(doctor["package"]["current"], current + 1)

    def test_07_failed_release_restores_skill_bytes_and_deletes_manifest(
        self,
    ) -> None:
        # A missing target guide is a safe public-filesystem fault: generation
        # fails after the release enters its restoration window, without
        # aliasing the output to another file that can be destructively written.
        current = self.current()
        skill_md = self.skill / "SKILL.md"
        skill_before = skill_md.read_bytes()
        target = self.skill / "manifests" / f"{current + 1}.json"
        self.assert_package_failure(
            self.cli(
                self.nested, "release", "--version", str(current + 1)
            ),
            "release",
            "release_failed",
        )
        self.assertEqual(skill_md.read_bytes(), skill_before)
        self.assertFalse(target.exists())

    def test_08_failed_release_restores_preexisting_target_inode_and_bytes(
        self,
    ) -> None:
        current = self.current()
        target = self.skill / "manifests" / f"{current + 1}.json"
        target_before = b"pre-existing exact-next manifest bytes\n"
        target.write_bytes(target_before)
        target_inode = target.stat().st_ino
        self.assertEqual(target.stat().st_nlink, 1)
        guide = self.skill / "migrations" / f"{current + 1}.md"
        guide.symlink_to(Path("..") / "manifests" / target.name)
        self.seal_current_package()
        version_sources = (
            self.skill / "SKILL.md",
            self.skill / "scripts" / "_orchestrate" / "cli.py",
        )
        source_bytes_before = {
            path: path.read_bytes() for path in version_sources
        }
        target_before = target.read_bytes()

        result = self.cli(
            self.nested, "release", "--version", str(current + 1)
        )

        self.assert_package_failure(result, "release", "release_failed")
        self.assertIn("doctor", result.stderr.lower())
        self.assertEqual(
            {path: path.read_bytes() for path in version_sources},
            source_bytes_before,
        )
        self.assertTrue(target.is_file())
        self.assertEqual(target.read_bytes(), target_before)
        self.assertEqual(target.stat().st_ino, target_inode)
        self.assertEqual(target.stat().st_nlink, 1)
        self.assertTrue(guide.is_symlink())
        self.assertEqual(guide.read_bytes(), target_before)

    def test_09_unsafe_preexisting_manifest_targets_are_atomic_refusals(
        self,
    ) -> None:
        for target_shape in ("symlink", "multi-link"):
            with self.subTest(target_shape=target_shape):
                self.activate_package(f"unsafe-target-{target_shape}")
                current = self.current()
                target = self.skill / "manifests" / f"{current + 1}.json"
                sibling = self.skill / f"{target_shape}-referent.bin"
                original = f"preserve {target_shape} bytes\n".encode()
                sibling.write_bytes(original)
                sibling_inode = sibling.stat().st_ino
                if target_shape == "symlink":
                    target.symlink_to(Path("..") / sibling.name)
                    target_inode = target.lstat().st_ino
                else:
                    os.link(sibling, target)
                    target_inode = target.stat().st_ino
                    self.assertEqual(target_inode, sibling_inode)
                    self.assertEqual(target.stat().st_nlink, 2)
                guide = self.skill / "migrations" / f"{current + 1}.md"
                guide.write_text("# Safe release target fixture\n", encoding="utf-8")
                self.seal_current_package()
                skill_md = self.skill / "SKILL.md"
                skill_before = skill_md.read_bytes()
                skill_inode = skill_md.stat().st_ino

                result = self.cli(
                    self.nested, "release", "--version", str(current + 1)
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
                payload = json_object(result.stderr)
                self.assertEqual(payload["ok"], False)
                self.assertEqual(payload["operation"], "release")
                self.assertEqual(payload["orchestrate_version"], CURRENT_VERSION)
                self.assertEqual(set(payload["error"]), {"code", "message"})
                self.assertIsInstance(payload["error"]["code"], str)
                self.assertTrue(payload["error"]["code"])
                self.assertIsInstance(payload["error"]["message"], str)
                self.assertTrue(payload["error"]["message"])
                self.assertEqual(skill_md.read_bytes(), skill_before)
                self.assertEqual(skill_md.stat().st_ino, skill_inode)
                self.assertEqual(sibling.read_bytes(), original)
                self.assertEqual(sibling.stat().st_ino, sibling_inode)
                self.assertEqual(target.read_bytes(), original)
                if target_shape == "symlink":
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(target.lstat().st_ino, target_inode)
                    self.assertEqual(os.readlink(target), f"../{sibling.name}")
                else:
                    self.assertFalse(target.is_symlink())
                    self.assertEqual(target.stat().st_ino, target_inode)
                    self.assertEqual(target.stat().st_ino, sibling.stat().st_ino)
                    self.assertEqual(target.stat().st_nlink, 2)

    def test_10_invalid_skill_version_is_a_doctor_predicate_and_blocks_mutation(
        self,
    ) -> None:
        for state in ("invalid-utf8", "missing-version", "missing-file"):
            with self.subTest(state=state):
                self.activate_package(f"skill-{state}")
                skill_md = self.skill / "SKILL.md"
                if state == "invalid-utf8":
                    skill_md.write_bytes(b"\xff\xfe\x00")
                elif state == "missing-version":
                    skill_md.write_text(
                        "---\nname: orchestrate\n---\n# Invalid fixture\n",
                        encoding="utf-8",
                    )
                else:
                    skill_md.unlink()
                before = self.managed_state_snapshot()

                doctor = self.cli(self.nested, "doctor")
                mutation = self.cli(self.nested, "pin", "set")

                with self.subTest(command="doctor"):
                    self.assertEqual(doctor.returncode, 1, doctor.stderr)
                    self.assertEqual(doctor.stderr, "")
                    self.assertNotIn("Traceback", doctor.stdout)
                    payload = json_object(doctor.stdout)
                    self.assertEqual(payload["ok"], False)
                    self.assertEqual(payload["operation"], "doctor")
                    self.assertEqual(payload["orchestrate_version"], CURRENT_VERSION)
                    self.assertIsInstance(payload.get("diagnostics"), list)
                    self.assertTrue(payload["diagnostics"])
                    for diagnostic in payload["diagnostics"]:
                        self.assertEqual(set(diagnostic), {"code", "message"})
                        self.assertEqual(diagnostic["code"], "manifest_invalid")
                        self.assertIsInstance(diagnostic["message"], str)
                        self.assertTrue(diagnostic["message"])
                with self.subTest(command="pin-set"):
                    self.assert_package_failure(
                        mutation, "pin-set", "package_unhealthy"
                    )
                    self.assertEqual(self.managed_state_snapshot(), before)

    def test_11_malformed_manifest_sections_refuse_doctor_and_diff(
        self,
    ) -> None:
        for shape in ("non-mapping", "missing", "non-string-hash"):
            with self.subTest(shape=shape):
                self.activate_package(f"sections-{shape}")
                current = self.current()
                path = self.skill / "manifests" / f"{current}.json"
                manifest = json.loads(path.read_text(encoding="utf-8"))
                document = manifest["documents"]["SKILL.md"]
                if shape == "non-mapping":
                    document["sections"] = []
                elif shape == "missing":
                    document.pop("sections")
                else:
                    document["sections"] = {"Fixture section": None}
                path.write_text(
                    json.dumps(manifest, sort_keys=True), encoding="utf-8"
                )
                manifest_before = path.read_bytes()
                skill_before = (self.skill / "SKILL.md").read_bytes()
                state_before = self.managed_state_snapshot()

                doctor = self.cli(self.nested, "doctor")
                diff = self.cli(
                    self.nested,
                    "doctor",
                    "diff",
                    str(current - 1),
                    str(current),
                )

                with self.subTest(command="doctor"):
                    self.assertEqual(doctor.returncode, 1, doctor.stderr)
                    self.assertEqual(doctor.stderr, "")
                    self.assertNotIn("Traceback", doctor.stdout)
                    payload = json_object(doctor.stdout)
                    self.assertEqual(payload["ok"], False)
                    self.assertEqual(payload["operation"], "doctor")
                    self.assertEqual(payload["orchestrate_version"], CURRENT_VERSION)
                    self.assertIsInstance(payload.get("diagnostics"), list)
                    self.assertTrue(payload["diagnostics"])
                    for diagnostic in payload["diagnostics"]:
                        self.assertEqual(set(diagnostic), {"code", "message"})
                        self.assertEqual(diagnostic["code"], "manifest_invalid")
                        self.assertIsInstance(diagnostic["message"], str)
                        self.assertTrue(diagnostic["message"])
                with self.subTest(command="doctor-diff"):
                    self.assert_package_failure(
                        diff, "doctor-diff", "manifest_invalid"
                    )
                self.assertEqual(path.read_bytes(), manifest_before)
                self.assertEqual(
                    (self.skill / "SKILL.md").read_bytes(), skill_before
                )
                self.assertEqual(self.managed_state_snapshot(), state_before)

    def test_12_profile_manifest_projects_only_identity_and_prompt(self) -> None:
        home = release.source_home(self.skill)
        profiles = release.build_manifest(self.skill, self.current())["profiles"]
        self.assertEqual(
            set(profiles),
            {
                path.relative_to(home).as_posix()
                for path in release.profile_paths(home)
                if path.is_file()
            },
        )
        for path, entry in profiles.items():
            with self.subTest(path=path):
                self.assertEqual(set(entry), {"agent_name", "prompt_sha256"})
                self.assertIsInstance(entry["agent_name"], str)
                self.assertTrue(entry["agent_name"])
                self.assertIsInstance(entry["prompt_sha256"], str)
                self.assertRegex(entry["prompt_sha256"], r"^[0-9a-f]{64}$")

        expected_shape = {"agent_name", "prompt_sha256"}
        if set(profiles[".codex/agents/lane-worker.toml"]) != expected_shape:
            return
        toml_path = home / ".codex" / "agents" / "lane-worker.toml"
        toml_entry = profiles[".codex/agents/lane-worker.toml"]
        toml_profile = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        self.assertEqual(toml_entry["agent_name"], toml_profile["name"])
        self.assertEqual(
            toml_entry["prompt_sha256"],
            hashlib.sha256(
                toml_profile["developer_instructions"].encode("utf-8")
            ).hexdigest(),
        )

        for relative in (
            ".claude/agents/lane-worker.md",
            ".pi/agent/agents/lane-worker.md",
        ):
            path = home / relative
            text = path.read_text(encoding="utf-8")
            frontmatter, prompt = text.split("\n---\n", 1)
            name = next(
                line.split(":", 1)[1].strip()
                for line in frontmatter.splitlines()
                if line.startswith("name:")
            )
            entry = profiles[relative]
            self.assertEqual(entry["agent_name"], name)
            self.assertEqual(
                entry["prompt_sha256"],
                hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            )

        append = home / ".pi" / "agent" / "APPEND_SYSTEM.md"
        append_entry = profiles[".pi/agent/APPEND_SYSTEM.md"]
        self.assertEqual(append_entry["agent_name"], "APPEND_SYSTEM")
        self.assertEqual(
            append_entry["prompt_sha256"],
            hashlib.sha256(append.read_bytes()).hexdigest(),
        )

    def test_13_profile_manifest_ignores_runtime_metadata_but_tracks_name_and_prompt(
        self,
    ) -> None:
        home = release.source_home(self.skill)
        baseline = release.build_manifest(self.skill, self.current())["profiles"]

        codex = home / ".codex" / "agents" / "lane-worker.toml"
        def regex_substitute_once(
            text: str, pattern: str, replacement: str
        ) -> str:
            updated, count = re.subn(
                pattern, replacement, text, count=1, flags=re.MULTILINE
            )
            self.assertEqual(count, 1, f"expected one match for {pattern!r}")
            return updated

        def exact_substitute_once(text: str, old: str, new: str) -> str:
            count = text.count(old)
            self.assertEqual(count, 1, f"expected one match for {old!r}")
            return text.replace(old, new, 1)

        codex = home / ".codex" / "agents" / "lane-worker.toml"
        codex_text = codex.read_text(encoding="utf-8")
        codex_text = regex_substitute_once(
            codex_text,
            r'^description\s*=\s*"[^"\r\n]+"$',
            'description = "metadata-only description"',
        )
        codex_text = regex_substitute_once(
            codex_text,
            r'^model\s*=\s*"[^"\r\n]+"$',
            'model = "metadata-only-model"',
        )
        codex_text = regex_substitute_once(
            codex_text,
            r'^model_reasoning_effort\s*=\s*"[^"\r\n]+"$',
            'model_reasoning_effort = "low"',
        )
        codex_text = regex_substitute_once(
            codex_text,
            r'^sandbox_mode\s*=\s*"[^"\r\n]+"$',
            'sandbox_mode = "read-only"',
        )
        codex_text = exact_substitute_once(
            codex_text,
            "developer_instructions = '''",
            'runtime_metadata = "metadata-only"\n\ndeveloper_instructions = \'\'\'',
        )
        codex.write_text(codex_text, encoding="utf-8")

        claude = home / ".claude" / "agents" / "lane-worker.md"
        claude_text = claude.read_text(encoding="utf-8")
        claude_text = regex_substitute_once(
            claude_text,
            r'^description:\s*.+$',
            "description: metadata-only description",
        )
        claude_text = regex_substitute_once(
            claude_text,
            r'^model:\s*.+$',
            "model: metadata-only-model",
        )
        claude_text = regex_substitute_once(
            claude_text,
            r'^color:\s*.+$',
            "color: metadata-only-color",
        )
        claude_text = regex_substitute_once(
            claude_text,
            r'^skills:\s*.+$',
            "skills: [metadata-only-skill]",
        )
        claude_text = exact_substitute_once(
            claude_text,
            "---\n# Lane Worker",
            "runtimeMetadata: metadata-only\n---\n# Lane Worker",
        )
        claude.write_text(claude_text, encoding="utf-8")

        pi = home / ".pi" / "agent" / "agents" / "lane-worker.md"
        pi_text = pi.read_text(encoding="utf-8")
        pi_text = regex_substitute_once(
            pi_text,
            r'^description:\s*.+$',
            "description: metadata-only description",
        )
        pi_text = regex_substitute_once(
            pi_text,
            r'^model:\s*.+$',
            "model: metadata-only-model",
        )
        pi_text = regex_substitute_once(
            pi_text,
            r'^thinking:\s*.+$',
            "thinking: low",
        )
        pi_text = regex_substitute_once(
            pi_text,
            r'^tools:\s*.+$',
            "tools: read",
        )
        pi_text = regex_substitute_once(
            pi_text,
            r'^async:\s*.+$',
            "async: false",
        )
        pi_text = exact_substitute_once(
            pi_text,
            "---\n# Lane Worker",
            "runtimeMetadata: metadata-only\n---\n# Lane Worker",
        )
        pi.write_text(pi_text, encoding="utf-8")

        metadata_only = release.build_manifest(self.skill, self.current())["profiles"]
        self.assertEqual(metadata_only, baseline)
        for entry in metadata_only.values():
            self.assertEqual(set(entry), {"agent_name", "prompt_sha256"})

        renamed = codex.read_text(encoding="utf-8").replace(
            'name = "lane-worker"', 'name = "renamed-lane-worker"', 1
        )
        codex.write_text(renamed, encoding="utf-8")
        name_changed = release.build_manifest(self.skill, self.current())["profiles"]
        codex_entry = ".codex/agents/lane-worker.toml"
        self.assertEqual(
            name_changed[codex_entry]["agent_name"], "renamed-lane-worker"
        )
        self.assertEqual(
            name_changed[codex_entry]["prompt_sha256"],
            baseline[codex_entry]["prompt_sha256"],
        )
        self.assertNotEqual(name_changed[codex_entry], baseline[codex_entry])

        updated_prompt = codex.read_text(encoding="utf-8").replace(
            "\n'''", "\nPrompt semantic amendment.\n'''", 1
        )
        codex.write_text(updated_prompt, encoding="utf-8")
        prompt_changed = release.build_manifest(self.skill, self.current())["profiles"]
        self.assertEqual(
            prompt_changed[codex_entry]["agent_name"], "renamed-lane-worker"
        )
        self.assertNotEqual(
            prompt_changed[codex_entry]["prompt_sha256"],
            name_changed[codex_entry]["prompt_sha256"],
        )

        claude_entry = ".claude/agents/lane-worker.md"
        claude.write_text(
            claude.read_text(encoding="utf-8").replace(
                "name: lane-worker", "name: renamed-lane-worker", 1
            ),
            encoding="utf-8",
        )
        markdown_name_changed = release.build_manifest(self.skill, self.current())[
            "profiles"
        ]
        self.assertEqual(
            markdown_name_changed[claude_entry]["agent_name"], "renamed-lane-worker"
        )
        self.assertEqual(
            markdown_name_changed[claude_entry]["prompt_sha256"],
            baseline[claude_entry]["prompt_sha256"],
        )
        claude.write_text(
            claude.read_text(encoding="utf-8") + "\nPrompt semantic amendment.\n",
            encoding="utf-8",
        )
        markdown_prompt_changed = release.build_manifest(self.skill, self.current())[
            "profiles"
        ]
        self.assertNotEqual(
            markdown_prompt_changed[claude_entry]["prompt_sha256"],
            markdown_name_changed[claude_entry]["prompt_sha256"],
        )

        append = home / ".pi" / "agent" / "APPEND_SYSTEM.md"
        append_entry = ".pi/agent/APPEND_SYSTEM.md"
        append.write_bytes(append.read_bytes() + b"\nPrompt semantic amendment.\n")
        append_changed = release.build_manifest(self.skill, self.current())["profiles"]
        self.assertEqual(append_changed[append_entry]["agent_name"], "APPEND_SYSTEM")
        self.assertNotEqual(
            append_changed[append_entry]["prompt_sha256"],
            baseline[append_entry]["prompt_sha256"],
        )

    def test_14_missing_or_non_string_profile_identity_or_prompt_is_unhealthy(
        self,
    ) -> None:
        home = release.source_home(self.skill)
        profile = home / ".codex" / "agents" / "lane-worker.toml"
        original = profile.read_text(encoding="utf-8")
        fixtures = {
            "missing-name": 'description = "fixture"\ndeveloper_instructions = "prompt"\n',
            "non-string-name": 'name = 7\ndeveloper_instructions = "prompt"\n',
            "missing-prompt": 'name = "lane-worker"\n',
            "non-string-prompt": 'name = "lane-worker"\ndeveloper_instructions = 7\n',
        }
        for shape, content in fixtures.items():
            with self.subTest(shape=shape):
                profile.write_text(content, encoding="utf-8")
                with self.assertRaises(release.OrchestrateError):
                    release.build_manifest(self.skill, self.current())
                doctor = self.cli(self.nested, "doctor")
                self.assertEqual(doctor.returncode, 1)
                self.assertEqual(doctor.stderr, "")
                self.assertNotIn("Traceback", doctor.stdout)
                payload = json_object(doctor.stdout)
                self.assertFalse(payload["ok"])
                self.assertTrue(payload["diagnostics"])
        profile.write_text(original, encoding="utf-8")

    def test_15_malformed_pin_refuses_status_and_set_without_mutation(self) -> None:
        for malformed in (b"{not-json\n", b"[137]\n"):
            with self.subTest(malformed=malformed):
                pin = self.pin_path()
                pin.parent.mkdir(parents=True, exist_ok=True)
                pin.write_bytes(malformed)
                pin_inode = pin.stat().st_ino
                before = self.managed_state_snapshot()

                observed = []
                for command, operation in (
                    (("pin", "status"), "pin-status"),
                    (("pin", "set"), "pin-set"),
                ):
                    result = self.cli(self.nested, *command)
                    observed.append(
                        (
                            operation,
                            result,
                            self.managed_state_snapshot(),
                            pin.read_bytes(),
                            pin.stat().st_ino,
                        )
                    )

                for operation, result, state, pin_bytes, inode in observed:
                    with self.subTest(malformed=malformed, command=operation):
                        self.assert_package_failure(
                            result, operation, "pin_invalid"
                        )
                        self.assertEqual(state, before)
                        self.assertEqual(pin_bytes, malformed)
                        self.assertEqual(inode, pin_inode)


class SourcePublicationContractTests(unittest.TestCase):
    """Contract E cases 8-13 at the shipped source/setup subprocess seams."""

    def test_09_current_manifests_are_matched_regenerable_and_doctor_valid(
        self,
    ) -> None:
        self.assertGreaterEqual(
            CURRENT_VERSION,
            140,
            "source package still identifies a pre-v140 release",
        )
        paths = [
            skill / f"manifests/{CURRENT_VERSION}.json"
            for skill in (CODEX_SKILL, PI_SKILL)
        ]
        for path in paths:
            self.assertTrue(path.is_file(), path)
        self.assertEqual(paths[0].read_bytes(), paths[1].read_bytes())

        current = json.loads(paths[0].read_text(encoding="utf-8"))
        previous = json.loads(
            (CODEX_SKILL / "manifests/137.json").read_text(encoding="utf-8")
        )
        self.assertEqual(current["skill_version"], CURRENT_VERSION)
        self.assertEqual(current["orchestrate_compat"], CURRENT_VERSION)
        self.assertTrue(current["documents"])
        self.assertNotIn("runtime_assets", current)
        # Since v142 the manifest binds only the profiles orchestrate dispatches,
        # so the roster is a subset of the historical one rather than equal to it.
        self.assertEqual(
            set(current["profiles"]),
            {
                path.relative_to(release.source_home(CODEX_SKILL)).as_posix()
                for path in release.profile_paths(release.source_home(CODEX_SKILL))
                if path.is_file()
            },
        )
        self.assertLessEqual(set(current["profiles"]), set(previous["profiles"]))
        for path, entry in current["profiles"].items():
            with self.subTest(profile=path):
                self.assertEqual(set(entry), {"agent_name", "prompt_sha256"})
                self.assertIsInstance(entry["agent_name"], str)
                self.assertTrue(entry["agent_name"])
                self.assertRegex(entry["prompt_sha256"], r"^[0-9a-f]{64}$")
        comparison = release.compare_manifests(previous, current)
        # Narrowing the roster removes entries; a surviving profile changes only
        # when a release deliberately rewrites its prompt. v143 gave lane-worker
        # codebase-design and diagnosing-bugs, so its three projections moved and
        # nothing else did.
        common = set(current["profiles"]) & set(previous["profiles"])
        self.assertEqual(
            sorted(name for name in comparison["changed_profiles"] if name in common),
            [
                ".claude/agents/lane-worker.md",
                ".codex/agents/lane-worker.toml",
                ".pi/agent/agents/lane-worker.md",
            ],
        )
        self.assertEqual(
            comparison["changed_runtime_assets"],
            [".pi/agent/extensions/orchestrate-pi.ts"],
        )

        with tempfile.TemporaryDirectory(prefix="orchestrate-regenerate-") as temporary:
            generated = []
            for index, skill in enumerate((CODEX_SKILL, PI_SKILL)):
                output = Path(temporary) / f"logical-{index}.json"
                release.write_release_manifest(
                    skill, CURRENT_VERSION, CURRENT_VERSION - 1, output
                )
                generated.append(output.read_bytes())
            self.assertEqual(generated, [paths[0].read_bytes()] * 2)

        for skill in (CODEX_SKILL, PI_SKILL):
            with self.subTest(doctor=skill):
                observed = release.verify_release(skill)
                self.assertTrue(observed["ok"], observed["errors"])

    def test_10_help_exposes_no_retired_lifecycle_surface(self) -> None:
        script = CODEX_SKILL / "scripts/orchestrate.py"
        help_text = []
        for argv in (
            (),
            ("lane",),
            ("integration",),
            ("acceptance",),
            ("timing",),
            ("pin",),
            ("doctor",),
        ):
            result = subprocess.run(
                [sys.executable, str(script), *argv, "--help"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            help_text.append(result.stdout)
        all_help = "\n".join(help_text)
        for retired in ("commit-check", "candidate", "--root", "--base", "--sha", "--final"):
            self.assertNotIn(retired, all_help)

    def test_11_setup_is_replacement_first_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrate-v137-setup-") as temporary:
            base = Path(temporary)
            source, home = setup_support.seed_source(base)
            retired = setup_support.seed_managed_retired_links(source, home)
            protected = home / ".config/private.conf"
            protected.parent.mkdir(parents=True, exist_ok=True)
            protected.write_bytes(b"protected installed bytes\n")
            source_before = {
                path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*")
                if path.is_file()
            }

            first = setup_support.run_setup(source, home)
            self.assertEqual(first.returncode, 0, first.stderr)
            first_snapshot = setup_support.snapshot_home(home)
            second = setup_support.run_setup(source, home)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(setup_support.snapshot_home(home), first_snapshot)
            self.assertEqual(protected.read_bytes(), b"protected installed bytes\n")
            for path in retired:
                self.assertFalse(path.exists() or path.is_symlink(), path)
            self.assertEqual(
                {
                    path.relative_to(source).as_posix(): path.read_bytes()
                    for path in source.rglob("*")
                    if path.is_file()
                },
                source_before,
            )

        for logical in ("codex",):
            with self.subTest(corrupt_logical=logical), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary)
                source, home = setup_support.seed_source(base)
                retired = setup_support.seed_managed_retired_links(source, home)
                manifest = (
                    source
                    / f"home/.codex/skills/orchestrate/manifests/{CURRENT_VERSION}.json"
                )
                self.assertTrue(manifest.is_file(), manifest)
                payload = json.loads(manifest.read_text(encoding="utf-8"))
                payload["documents"]["runtime-pi.md"]["sha256"] = "0" * 64
                manifest.write_text(json.dumps(payload), encoding="utf-8")

                result = setup_support.run_setup(source, home)

                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(
                    f"{logical} release verification failed", result.stderr.lower()
                )
                for path in retired:
                    self.assertTrue(path.is_symlink(), path)

    def test_12_installed_help_and_lifecycle_match_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orchestrate-v137-installed-") as temporary:
            base = Path(temporary)
            source, home = setup_support.seed_source(base)
            setup = setup_support.run_setup(source, home)
            self.assertEqual(setup.returncode, 0, setup.stderr)

            source_script = source / "home/.codex/skills/orchestrate/scripts/orchestrate.py"
            installed_script = home / ".codex/skills/orchestrate/scripts/orchestrate.py"
            self.assertTrue(os.path.samefile(source_script, installed_script))
            source_help = subprocess.run(
                [sys.executable, str(source_script), "--help"],
                cwd=base,
                text=True,
                capture_output=True,
                check=False,
            )
            installed_help = subprocess.run(
                [sys.executable, str(installed_script), "--help"],
                cwd=base,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(installed_help.returncode, 0, installed_help.stderr)
            self.assertEqual(installed_help.stdout, source_help.stdout)
            for retired in ("commit-check", "candidate", "--root", "--base", "--sha", "--final"):
                self.assertNotIn(retired, installed_help.stdout)

            repository = base / "repository"
            repository.mkdir()
            git_env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "Installed Contract",
                "GIT_AUTHOR_EMAIL": "installed@example.invalid",
                "GIT_COMMITTER_NAME": "Installed Contract",
                "GIT_COMMITTER_EMAIL": "installed@example.invalid",
            }

            def git(*argv: str) -> str:
                result = subprocess.run(
                    ["git", *argv],
                    cwd=repository,
                    env=git_env,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()

            def cli(*argv: str) -> dict[str, Any]:
                result = subprocess.run(
                    [sys.executable, str(installed_script), *argv],
                    cwd=repository,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json_object(result.stdout)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["orchestrate_version"], CURRENT_VERSION)
                return payload

            git("init", "-q", "-b", "main")
            (repository / "base.txt").write_text("base\n", encoding="utf-8")
            git("add", "base.txt")
            git("commit", "-qm", "base")
            cli("integration", "create", "--task-id", "installed-contract")
            cli("lane", "create", "--task-id", "installed-contract", "--lane-id", "tracer")
            lane = repository / ".agent_state/worktrees/installed-contract/lanes/tracer"
            (lane / "delivered.txt").write_text("delivered\n", encoding="utf-8")
            subprocess.run(["git", "add", "delivered.txt"], cwd=lane, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "installed tracer"],
                cwd=lane,
                env=git_env,
                check=True,
            )
            cli("lane", "check", "--task-id", "installed-contract", "--lane-id", "tracer")
            cli("integration", "collect", "--task-id", "installed-contract", "--lane-id", "tracer")
            cli("acceptance", "start", "--task-id", "installed-contract")
            cli("acceptance", "result", "--task-id", "installed-contract", "--outcome", "pass")
            cli("integration", "land", "--task-id", "installed-contract", "--persist", "main")
            cli("integration", "remove", "--task-id", "installed-contract", "--no-report")
            self.assertEqual((repository / "delivered.txt").read_text(), "delivered\n")
            self.assertEqual(
                git("for-each-ref", "--format=%(refname)", "refs/orchestrate/installed-contract/"),
                "",
            )
            self.assertEqual(
                git("for-each-ref", "--format=%(refname)", "refs/heads/wave/installed-contract/"),
                "",
            )

            rerun = setup_support.run_setup(source, home)
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
