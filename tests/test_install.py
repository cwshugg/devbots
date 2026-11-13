"""Focused installer checks in isolated homes, never the user's Copilot paths."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Invoke the real entry point from outside its checkout.
ROOT = Path(__file__).resolve().parents[1]


class NativeInstall(unittest.TestCase):
    """Check native assets, file conflicts, and unsafe destinations."""

    def setUp(self) -> None:
        """Allocate a private home for every subprocess."""
        temporary = tempfile.TemporaryDirectory(prefix="devbots install ")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.destination = self.home / ".copilot"

    def install(self, *args: str, code: int = 0) -> str:
        """Run the actual CLI with a private HOME and explicit exit check."""
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "install.py"), *args],
            cwd=self.home,
            env={
                **os.environ,
                "HOME": str(self.home),
                "USERPROFILE": str(self.home),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            result.returncode, code, result.stdout + result.stderr
        )
        if code:
            self.assertNotIn("Copied:", result.stdout)
        return result.stdout + result.stderr

    def test_native_assets_and_installed_workflow(self) -> None:
        """Resolve installed references and run all three collaboration CLIs."""
        output = self.install()
        self.assertIn("14 copied, 0 unchanged", output)
        agents = sorted((self.destination / "agents").glob("*.agent.md"))
        self.assertEqual(len(agents), 7)
        director = self.destination / "agents/devbots-director.agent.md"
        self.assertEqual(
            set(re.findall(r"`(devbots-[a-z]+)`", director.read_text())),
            {path.name.removesuffix(".agent.md") for path in agents},
        )
        for path in agents:
            text = path.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            self.assertIn('name: "[Devbots::', frontmatter)
            self.assertIn("description:", frontmatter)
            self.assertNotIn("devbots:", text)
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if link.startswith(("https://", "http://")):
                    continue
                self.assertTrue((path.parent / link).is_file(), link)
        skills = self.destination / "skills"
        for path in skills.glob("*/SKILL.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn(f"name: {path.parent.name}\n", text)
            for link in re.findall(r"\]\(([^)]+)\)", text):
                self.assertTrue((path.parent / link).is_file(), link)
        for path in skills.rglob("*"):
            if path.is_file():
                source = ROOT / path.relative_to(self.destination)
                self.assertEqual(path.read_bytes(), source.read_bytes())
        self.assertFalse(
            (self.destination / "agents/.documenter.agent.md.swo").exists()
        )

        def cli(tool: str, *args: str, body: str = ""):
            """Invoke an installed launcher from an unrelated directory."""
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(skills / f"devbots-{tool}-cli" / f"{tool}-cli.py"),
                    "--json",
                    *args,
                ],
                cwd=self.home,
                input=body,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        cli("workspace", "init")
        task = cli(
            "tasks",
            "create",
            "--title",
            "Installed task",
            "--author",
            "Chief",
            "--owner",
            "Byteboy",
            body="Implement.",
        )
        cli(
            "tasks",
            "add-discussion",
            "--id",
            task["id"],
            "--author",
            "Byteboy",
            body="Verified.",
        )
        final = cli(
            "tasks", "set-status", "--id", task["id"], "--status", "done"
        )
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["discussions"][0]["body"], "Verified.")
        report = cli(
            "reports",
            "create",
            "--title",
            "Evidence",
            "--author",
            "Byteboy",
            body="Installed CLI works.",
        )
        self.assertEqual(
            cli("reports", "get", "--id", report["id"])["body"],
            "Installed CLI works.",
        )

    def test_logging_rerun_overwrite_and_preflight_conflict(self) -> None:
        """Log each path, preserve identical files, and protect conflicts."""
        first = self.install("--destination", str(self.destination))
        copied = [
            line for line in first.splitlines() if line.startswith("Copied:")
        ]
        self.assertEqual(len(copied), 14)
        for line in copied:
            source, target = line.removeprefix("Copied: ").split(" -> ")
            self.assertTrue(Path(source).is_file())
            self.assertTrue(Path(target).is_file())
        target = self.destination / "agents/devbots-director.agent.md"
        original = target.read_bytes()
        before = target.stat().st_mtime_ns
        for args in ((), ("--no-overwrite",)):
            output = self.install(*args)
            self.assertIn("0 copied, 14 unchanged", output)
            self.assertEqual(
                output.splitlines()[:-1],
                [line.replace("Copied:", "Unchanged:", 1) for line in copied],
            )
        self.assertEqual(target.stat().st_mtime_ns, before)
        keep = self.destination / "skills/keep.txt"
        keep.write_text("unrelated", encoding="utf-8")
        target.write_text("custom", encoding="utf-8")
        missing = self.destination / "skills/devbots_common.py"
        missing.unlink()
        self.assertIn("Conflict:", self.install("--no-overwrite", code=1))
        self.assertEqual(target.read_text(encoding="utf-8"), "custom")
        self.assertFalse(missing.exists())
        self.assertIn("2 copied, 12 unchanged", self.install())
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(keep.read_text(encoding="utf-8"), "unrelated")

    def test_linked_traversing_and_overlapping_destinations_fail(self) -> None:
        """Reject unsafe paths without writing any payload files."""
        outside = self.home / "outside"
        outside.mkdir()
        self.destination.symlink_to(outside, target_is_directory=True)
        self.assertIn("Linked path", self.install(code=1))
        self.assertEqual(list(outside.iterdir()), [])
        self.destination.unlink()
        self.install("--destination", str(outside / "../escape"), code=1)
        self.install("--destination", str(ROOT / "nested"), code=1)
        self.assertFalse((ROOT / "nested").exists())
        self.install()
        target = self.destination / "skills/devbots_common.py"
        target.unlink()
        victim = outside / "keep.py"
        victim.write_text("keep", encoding="utf-8")
        target.symlink_to(victim)
        self.install(code=1)
        target.unlink()
        os.link(victim, target)
        self.install(code=1)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
