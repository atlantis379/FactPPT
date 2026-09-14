import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.governance.check import ROOT, SKIP_PATTERN, check_initial_baseline, check_line_endings_policy, check_manifest, check_manifest_change, check_paths, check_registry, check_test_integrity, has_executable_skip, test_inventory


class TestGovernance(unittest.TestCase):
    def test_manifest(self):
        check_manifest()

    def test_lf_attributes(self):
        check_line_endings_policy()
        import subprocess
        result = subprocess.check_output(["git", "check-attr", "eol", "--", "docs/specs/SYSTEM_SPEC_v0.3.md", "schemas/frozen_manifest.json"], cwd=ROOT, text=True)
        self.assertEqual(result.count("eol: lf"), 2)

    def test_manifest_rejects_changed_hash_and_unlisted_artifact(self):
        actual = json.loads((ROOT / "schemas/frozen_manifest.json").read_text(encoding="utf-8"))
        with patch("tools.governance.check.json.loads", return_value={"artifacts": {}}):
            with self.assertRaisesRegex(ValueError, "empty"):
                check_manifest()
        damaged = {**actual, "artifacts": {**actual["artifacts"], "schemas/v0_2/new.json": "0" * 64}}
        with patch("tools.governance.check.json.loads", return_value=damaged):
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                check_manifest()
        name = next(iter(actual["artifacts"]))
        damaged = {**actual, "artifacts": {**actual["artifacts"], name: "0" * 64}}
        with patch("tools.governance.check.json.loads", return_value=damaged):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                check_manifest()

    def test_paths(self):
        check_paths(["tools/governance/check.py", "tests/governance/test_check.py"])
        for path in ("src/core.py", "docs/specs/SYSTEM_SPEC_v0.3.md", "schemas/v0_2/new.json", "../escape"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                check_paths([path])

    def test_inactive_milestone_rejected(self):
        with patch("pathlib.Path.read_text", return_value="**status:** NOT_CONFIGURED\n## Allowed paths\n- x\n## Forbidden paths\n- y\n"):
            with self.assertRaisesRegex(ValueError, "not ACTIVE"):
                check_paths(["x"])

    def test_frozen_requires_evidence(self):
        contract = (ROOT / "docs/milestones/CURRENT.md").read_text(encoding="utf-8").replace("**status:** ACTIVE", "**status:** FROZEN")
        with patch("pathlib.Path.read_text", return_value=contract):
            with self.assertRaisesRegex(ValueError, "unchecked acceptance"):
                check_paths(["tools/governance/check.py"])
        contract = contract.replace("- [ ]", "- [x]")
        with patch("pathlib.Path.read_text", return_value=contract):
            with self.assertRaisesRegex(ValueError, "lacks completion or audit"):
                check_paths(["tools/governance/check.py"])

    def test_frozen_with_evidence_allows_governance_path(self):
        contract = (ROOT / "docs/milestones/CURRENT.md").read_text(encoding="utf-8").replace("**status:** ACTIVE", "**status:** FROZEN").replace("- [ ]", "- [x]")
        report = "**status:** COMPLETE\n- tests: PASS\n- ci: PASS\n- golden: PASS\n- frozen_hash: PASS\n"
        audit = "milestone_id: M0\nresult: PASS\nfindings: []\n"
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if str(path).endswith("CURRENT.md"):
                return contract
            if str(path).endswith("M0_FINAL.md"):
                return report
            if str(path).endswith("M0_AUDIT.yaml"):
                return audit
            return original(path, *args, **kwargs)
        with patch("pathlib.Path.read_text", new=read_text), patch("pathlib.Path.is_file", return_value=True):
            check_paths(["tools/governance/check.py"])

    def test_registry(self):
        check_registry()

    def test_push_baseline_selection(self):
        workflow = (ROOT / ".github/workflows/governance.yml").read_text(encoding="utf-8")
        self.assertIn('git rev-list --count HEAD', workflow)
        self.assertIn('origin/$DEFAULT_BRANCH', workflow)
        self.assertIn('"$PUSH_BEFORE"', workflow)
        self.assertNotIn('--base HEAD^', workflow)

    def test_test_integrity(self):
        with patch("tools.governance.check.git_lines", return_value=[]):
            check_test_integrity("base")
        with patch("tools.governance.check.git_lines", return_value=["D\ttests/old.py"]):
            with self.assertRaisesRegex(ValueError, "tests deleted"):
                check_test_integrity("base")
        with patch("tools.governance.check.git_lines", return_value=["R100\ttests/old.py\tarchive/old.py"]):
            with self.assertRaisesRegex(ValueError, "tests deleted"):
                check_test_integrity("base")
        with patch("tools.governance.check.git_lines", return_value=["M\ttests/old.py"]):
            with patch("tools.governance.check.git_text", return_value="def test_old():\n    assert 1\n"), patch("pathlib.Path.read_text", return_value="def test_old():\n    pass\n"):
                with self.assertRaisesRegex(ValueError, "weakened"):
                    check_test_integrity("base")

    def test_inventory_detects_removed_or_weakened_assertions(self):
        self.assertEqual(test_inventory("def test_x():\n    assert 1\n    assert 2\n"), {"test_x": 2})

    def test_modified_test_can_strengthen(self):
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            return "def test_old():\n    assert 1\n    assert 2\n" if str(path).endswith("old.py") else original(path, *args, **kwargs)
        with patch("tools.governance.check.git_lines", return_value=["M\ttests/old.py"]), patch("tools.governance.check.git_text", return_value="def test_old():\n    assert 1\n"), patch("pathlib.Path.read_text", new=read_text):
            check_test_integrity("base")

    def test_modified_test_rejects_removed_function(self):
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            return "def test_other():\n    assert 1\n" if str(path).endswith("old.py") else original(path, *args, **kwargs)
        with patch("tools.governance.check.git_lines", return_value=["M\ttests/old.py"]), patch("tools.governance.check.git_text", return_value="def test_old():\n    assert 1\n"), patch("pathlib.Path.read_text", new=read_text):
            with self.assertRaisesRegex(ValueError, "weakened"):
                check_test_integrity("base")

    def test_skip_variants(self):
        for source in ("@unittest." + "skipIf(True, 'x')", "@unittest." + "skipUnless(False, 'x')", "@pytest.mark." + "skipif(True)", "pytest." + "skip('x')"):
            with self.subTest(source=source):
                self.assertRegex(source, SKIP_PATTERN)
                executable = source + "\ndef test_x(): pass\n" if source.startswith("@") else source
                self.assertTrue(has_executable_skip(executable))

    def test_skip_examples_in_strings_are_not_executable(self):
        source = "def test_example():\n    example = \"@unittest." + "skipIf(True, 'x')\"\n    assert example\n"
        self.assertFalse(has_executable_skip(source))
        self.assertTrue(has_executable_skip("def test_x():\n    pytest." + "skip('x')\n"))

    def test_manifest_change_rejected(self):
        prior = {"artifacts": {"docs/specs/a.md": "0" * 64}}
        current = {"artifacts": {"docs/specs/a.md": "1" * 64}}
        cr = "**status:** APPROVED\n**affected_artifact:** docs/specs/a.md\napproved_by: Reviewer\napproved_at: 2026-09-14\n"
        def lines(args, root=ROOT):
            if args[0] == "ls-tree":
                return ["docs/change_requests/CR-1.md"]
            return ["schemas/frozen_manifest.json"] if args[-1] == "schemas/frozen_manifest.json" else []
        def texts(args, root=ROOT):
            return json.dumps(prior) if args[-1].endswith("frozen_manifest.json") else cr
        with patch("tools.governance.check.git_lines", side_effect=lines), patch("tools.governance.check.git_text", side_effect=texts), patch("pathlib.Path.read_text", return_value=json.dumps(current)):
            check_manifest_change("base")
        with patch("tools.governance.check.git_lines", side_effect=lines), patch("tools.governance.check.git_text", side_effect=lambda args, root=ROOT: json.dumps(prior) if args[-1].endswith("frozen_manifest.json") else cr.replace("APPROVED", "PROPOSED")), patch("pathlib.Path.read_text", return_value=json.dumps(current)):
            with self.assertRaisesRegex(ValueError, "APPROVED CR"):
                check_manifest_change("base")
        def changed_cr(args, root=ROOT):
            if args[0] == "ls-tree":
                return ["docs/change_requests/CR-1.md"]
            return ["schemas/frozen_manifest.json"] if args[-1] == "schemas/frozen_manifest.json" else ["docs/change_requests/CR-1.md"]
        with patch("tools.governance.check.git_lines", side_effect=changed_cr), patch("tools.governance.check.git_text", side_effect=texts), patch("pathlib.Path.read_text", return_value=json.dumps(current)):
            with self.assertRaisesRegex(ValueError, "APPROVED CR"):
                check_manifest_change("base")

    def test_initial_baseline_scope(self):
        def git_lines(args, root=ROOT):
            return ["1"] if args[0] == "rev-list" else ["docs/specs/DEVELOPMENT_CONTRACT.md", "src/rogue.py"]
        with patch("tools.governance.check.git_lines", side_effect=git_lines):
            with self.assertRaisesRegex(ValueError, "outside milestone"):
                check_initial_baseline()
        with patch("tools.governance.check.git_lines", return_value=["2"]):
            with self.assertRaisesRegex(ValueError, "root commit"):
                check_initial_baseline()

    def test_initial_baseline_rejects_skipped_test(self):
        def git_lines(args, root=ROOT):
            return ["1"] if args[0] == "rev-list" else ["tests/governance/skipped.py"]
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            return "@unittest." + "skipIf(True, 'x')\ndef test_skipped(): pass\n" if str(path).endswith("skipped.py") else original(path, *args, **kwargs)
        with patch("tools.governance.check.git_lines", side_effect=git_lines), patch("pathlib.Path.read_text", new=read_text):
            with self.assertRaisesRegex(ValueError, "test skip"):
                check_initial_baseline()


if __name__ == "__main__":
    unittest.main()
