"""Small end-to-end smoke suite for the public collaboration CLIs."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[1] / "skills"


class CollaborationSmoke(unittest.TestCase):
    """Exercise installed-path launchers from an unrelated working directory."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.cwd = Path(self.temporary.name)
        self.workspace = self.cwd / ".devbots"
        self.run_cli("workspace", "init", "--name", "Smoke: café")

    def invoke(
        self,
        tool: str,
        *args: str,
        body: str = "",
        explicit: bool = True,
        as_json: bool = True,
    ) -> subprocess.CompletedProcess:
        command = [
            sys.executable,
            "-B",
            str(SKILLS / f"devbots-{tool}-cli" / f"{tool}-cli.py"),
        ]
        if explicit:
            command.extend(("--workspace-path", str(self.workspace)))
        if as_json:
            command.append("--json")
        command.extend(args)
        result = subprocess.run(
            command,
            check=False,
            input=body.encode("utf-8"),
            cwd=self.cwd,
            capture_output=True,
            timeout=10,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            result.stdout.decode("utf-8").replace("\r\n", "\n"),
            result.stderr.decode("utf-8").replace("\r\n", "\n"),
        )

    def run_cli(self, tool: str, *args: str, **kwargs):
        result = self.invoke(tool, *args, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def test_task_handoff_status_owner_links_and_discussion(self) -> None:
        task = self.run_cli(
            "tasks",
            "create",
            "--title",
            "Feature: café",
            "--author",
            "Chief",
            "--owner",
            "Byteboy",
            body="Implement the approved design.",
        )
        review = self.run_cli(
            "tasks",
            "create",
            "--title",
            "Review",
            "--author",
            "Chief",
            "--linked-tasks",
            task["id"],
            "--empty",
        )
        self.assertEqual(review["linked_tasks"], [task["id"]])
        prefix = task["id"][:8]
        self.run_cli("tasks", "set-status", "--id", prefix, "--status", "underway")
        self.run_cli("tasks", "set-owner", "--id", prefix, "--owner", "Scribs")
        discussion = self.run_cli(
            "tasks",
            "add-discussion",
            "--id",
            prefix,
            "--author",
            "Byteboy",
            body="Evidence: tests pass 🧪",
        )
        self.assertEqual(
            discussion["discussions"][0]["body"], "Evidence: tests pass 🧪"
        )
        rows = self.run_cli(
            "tasks", "list", "--status", "underway", "--owner", "Scribs"
        )
        self.assertEqual([row["id"] for row in rows], [task["id"]])
        self.run_cli("tasks", "add-link", "--id", prefix, "--link-id", review["id"])
        self.run_cli("tasks", "remove-link", "--id", prefix, "--link-id", review["id"])
        self.run_cli("tasks", "set-status", "--id", prefix, "--status", "done")
        final = self.run_cli("tasks", "get", "--id", prefix)
        self.assertEqual(final["status"], "done")
        self.assertEqual(final["body"], task["body"])
        self.assertEqual(final["linked_tasks"], [])
        self.assertEqual(final["created"], task["created"])
        self.assertGreater(final["updated"], task["updated"])
        self.assertEqual(final["discussions"], discussion["discussions"])

    def test_report_workflow(self) -> None:
        result = self.invoke(
            "reports",
            "create",
            "--title",
            "Research",
            "--author",
            "Lorey",
            body="Sources and findings: café.",
            as_json=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report_path = Path(result.stdout.strip())
        self.assertTrue(report_path.is_file())
        report = self.run_cli("reports", "get", "--id", report_path.name[:8])
        self.assertEqual(report["body"], "Sources and findings: café.")
        report_path.write_bytes(report_path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(
            self.run_cli("reports", "get", "--id", report["id"])["body"], report["body"]
        )
        reports = self.run_cli("reports", "list")
        self.assertEqual([row["id"] for row in reports], [report["id"]])
        self.assertEqual(Path(reports[0]["path"]), report_path)

    def test_workspace_selection_and_ignore_conflict(self) -> None:
        project_ignore = self.cwd / ".gitignore"
        project_ignore.write_text("keep-me\n", encoding="utf-8")
        self.run_cli("workspace", "config", "--name", "Renamed")
        self.run_cli("workspace", "init")
        self.assertEqual(self.run_cli("workspace", "show")["config"]["name"], "Renamed")
        child = self.cwd / "child"
        child.mkdir()
        self.cwd = child
        missing = self.invoke("workspace", "show", explicit=False)
        self.assertNotEqual(missing.returncode, 0)
        self.assertFalse((child / ".devbots").exists())
        local = self.run_cli("workspace", "init", explicit=False)
        self.assertEqual(Path(local["workspace"]), child / ".devbots")
        self.assertEqual(project_ignore.read_text(encoding="utf-8"), "keep-me\n")
        conflict = self.cwd / "conflict"
        conflict.mkdir()
        (conflict / ".gitignore").write_text("preserve\n", encoding="utf-8")
        self.workspace = conflict
        denied = self.invoke("workspace", "init")
        self.assertNotEqual(denied.returncode, 0)
        self.assertEqual(list(conflict.iterdir()), [conflict / ".gitignore"])
        self.assertEqual(
            (conflict / ".gitignore").read_text(encoding="utf-8"), "preserve\n"
        )

    def test_config_contains_only_name_and_preserves_unsupported_data(self) -> None:
        config_path = self.workspace / "devbots-config.json"
        self.assertEqual(
            json.loads(config_path.read_text(encoding="utf-8")), {"name": "Smoke: café"}
        )
        self.assertEqual(
            self.run_cli("workspace", "show")["config"], {"name": "Smoke: café"}
        )
        self.run_cli("workspace", "init")
        self.assertEqual(
            self.run_cli("workspace", "config", "--name", "Renamed")["config"],
            {"name": "Renamed"},
        )
        for invalid in (
            {"name": "Keep", "version": 1},
            {"name": "Keep", "extra": ["data"]},
            {"name": ""},
            {"name": 1},
            {},
            [],
        ):
            with self.subTest(config=invalid):
                original = json.dumps(invalid).encode("utf-8")
                config_path.write_bytes(original)
                for command in (("show",), ("init",), ("config", "--name", "Lost")):
                    result = self.invoke("workspace", *command)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(config_path.read_bytes(), original)

    def test_discussions_are_lossless_markdown_and_survive_mutations(self) -> None:
        description = (
            "\n# Description 🧪\n\n  indented  \n"
            "## 2026-11-12T21:00:00.000000+00:00 - Not a discussion\n\n"
            "<!-- devbots-section: 0 -->\n\n---\n"
        )
        task = self.run_cli(
            "tasks", "create", "--title", "Markdown", "--author", "Chief",
            body=description,
        )
        path = Path(task["path"])
        self.assertEqual(task["body"], description)
        self.assertEqual(task["discussions"], [])
        bodies = [
            "\n  Preserve leading/trailing whitespace  \n\n",
            "## 2026-11-12T21:00:00.000000+00:00 - Embedded - author\n\n"
            "A heading is not an entry.\n\n<!-- devbots-section: 0 -->\n\n"
            "```markdown\n## fake\n```\n\n---\n* list\n> quote\n\ncafé 🧪",
            "Repeated body.",
            "Repeated body.",
            "Unclosed fence:\n```\n## text\n<!-- devbots-section: 999 -->",
            "CRLF\r\nlines\r\nwith a bare CR\rand tabs\t  \r\n",
        ]
        expected = []
        for body in bodies:
            previous = path.read_bytes().split(b"\n---\n", 1)[1]
            result = self.run_cli(
                "tasks", "add-discussion", "--id", task["id"],
                "--author", "Byteboy: café - author", body=body,
            )
            # Only frontmatter changes; previous Markdown is a byte-exact prefix.
            raw = path.read_bytes()
            frontmatter, markdown = raw.split(b"\n---\n", 1)
            self.assertNotIn("discussions", json.loads(frontmatter[4:]))
            self.assertTrue(markdown.startswith(previous))
            entry = result["discussions"][-1]
            expected.append(entry)
            self.assertEqual(entry["body"], body)
            self.assertEqual(entry["author"], "Byteboy: café - author")
            self.assertIn(
                f"## {entry['created']} - {entry['author']}\n\n".encode("utf-8"),
                markdown,
            )
            self.assertEqual(result["body"], description)
            self.assertEqual(result["discussions"], expected)
            self.assertEqual(
                self.run_cli("tasks", "get", "--id", task["id"])["discussions"],
                expected,
            )
        # Identical timestamps/authors/bodies must not merge or deduplicate entries.
        section = (
            f"## {expected[-1]['created']} - {expected[-1]['author']}\n\n"
            + expected[-1]["body"]
        )
        with path.open("ab") as stream:
            stream.write(
                f"<!-- devbots-section: {len(section)} -->\n{section}\n\n".encode(
                    "utf-8"
                )
            )
        expected.append(expected[-1].copy())
        markdown = path.read_bytes().split(b"\n---\n", 1)[1]
        for command in (
            ("set-status", "--status", "done"),
            ("set-owner", "--owner", "Scribs"),
        ):
            self.run_cli("tasks", command[0], "--id", task["id"], *command[1:])
            self.assertEqual(path.read_bytes().split(b"\n---\n", 1)[1], markdown)
        final = self.run_cli("tasks", "get", "--id", task["id"])
        self.assertEqual(final["body"], description)
        self.assertEqual(final["discussions"], expected)
        self.assertEqual(self.run_cli("tasks", "list")[0]["discussions"], expected)
        human = self.invoke("tasks", "get", "--id", task["id"], as_json=False)
        self.assertEqual(human.returncode, 0, human.stderr)
        for entry in expected:
            self.assertIn(
                f"## {entry['created']} - {entry['author']}\n\n", human.stdout
            )

    def test_invalid_discussion_inputs_leave_task_unchanged(self) -> None:
        task = self.run_cli(
            "tasks", "create", "--title", "Guard", "--author", "Chief", "--empty",
        )
        path = Path(task["path"])
        original = path.read_bytes()
        for author, body in (
            ("", "valid"), (" \t", "valid"), ("a\nb", "valid"),
            ("a\u2028b", "valid"), ("a\u2029b", "valid"), ("a\x85b", "valid"),
            ("a\x7fb", "valid"),
            ("Chief", ""), ("Chief", " \n\t "),
        ):
            with self.subTest(author=author, body=body):
                result = self.invoke(
                    "tasks", "add-discussion", "--id", task["id"],
                    "--author", author, body=body,
                )
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(result.stdout, "")
                self.assertEqual(path.read_bytes(), original)
        accepted = self.run_cli(
            "tasks", "add-discussion", "--id", task["id"],
            "--author", "Chief", body="An entry after an empty description.\n",
        )
        self.assertEqual(accepted["body"], "")
        self.assertEqual(len(accepted["discussions"]), 1)
        self.assertEqual(
            self.run_cli("tasks", "get", "--id", task["id"])["body"], ""
        )

    def test_old_or_corrupt_task_format_is_rejected_without_rewriting(self) -> None:
        task = self.run_cli(
            "tasks", "create", "--title", "Guard", "--author", "Chief",
            body="Description\n",
        )
        path = Path(task["path"])
        frontmatter, _ = path.read_bytes().split(b"\n---\n", 1)
        metadata = json.loads(frontmatter[4:])
        legacy = {
            **metadata,
            "discussions": [
                {"author": "Chief", "created": "2026-11-12T21:00:00.000000+00:00",
                 "body": "Existing evidence must not disappear."}
            ],
        }
        corrupt = [
            "---\n" + json.dumps(legacy) + "\n---\n\nOriginal description\n",
            frontmatter.decode("utf-8") + "\n---\n\nUnframed description\n",
            frontmatter.decode("utf-8")
            + "\n---\n\n<!-- devbots-section: 999 -->\nshort\n\n",
            path.read_bytes().decode("utf-8") + "Trailing unframed data\n",
        ]
        for heading in (
            "## not-a-time - Chief",
            "## 2026-02-30T21:00:00.000000+00:00 - Chief",
            "## 2026-11-12T21:00:00.000000+02:00 - Chief",
            "## 2026-11-12T21:00:00.000000+00:00 - ",
            "## 2026-11-12T21:00:00.000000+00:00 - a\u2028b",
        ):
            section = heading + "\n\nEvidence"
            corrupt.append(
                frontmatter.decode("utf-8") + "\n---\n\n"
                "<!-- devbots-section: 11 -->\nDescription\n\n"
                f"<!-- devbots-section: {len(section)} -->\n{section}\n\n"
            )
        for text in corrupt:
            with self.subTest(text=text):
                original = text.encode("utf-8")
                path.write_bytes(original)
                for args in (
                    ("get", "--id", task["id"]),
                    ("list",),
                    ("set-owner", "--id", task["id"], "--owner", "Lost"),
                    ("add-discussion", "--id", task["id"], "--author", "Chief"),
                ):
                    result = self.invoke("tasks", *args, body="New evidence")
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(path.read_bytes(), original)

    def test_readme_record_examples_are_readable(self) -> None:
        readme = (SKILLS.parent / "README.md").read_text(encoding="utf-8")
        examples = re.findall(r"```markdown\n(.*?)\n```", readme, re.DOTALL)
        self.assertEqual(len(examples), 2)
        for kind, example in zip(("tasks", "reports"), examples):
            metadata = json.loads(example.split("\n---\n", 1)[0][4:])
            singular = kind[:-1]
            path = self.workspace / kind / f"{metadata['id']}.{singular}.md"
            path.write_text(example + "\n", encoding="utf-8", newline="\n")
            result = self.run_cli(kind, "get", "--id", metadata["id"])
            self.assertEqual(result["id"], metadata["id"])
            self.assertTrue(result["body"].strip())
            self.assertEqual(len(self.run_cli(kind, "list")), 1)
            if kind == "tasks":
                self.assertNotIn("discussions", metadata)
                self.assertEqual(len(result["discussions"]), 1)

    def test_unsafe_ids_linked_paths_and_malformed_records_fail(self) -> None:
        denied = self.invoke("tasks", "get", "--id", "../outside")
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("hexadecimal", denied.stderr)
        task = self.run_cli(
            "tasks",
            "create",
            "--title",
            "Guard",
            "--author",
            "Chief",
            "--empty",
        )
        target = Path(task["path"])
        target.write_text("broken frontmatter\n", encoding="utf-8")
        malformed = self.invoke("tasks", "list")
        self.assertNotEqual(malformed.returncode, 0)
        self.assertIn("frontmatter", malformed.stderr)
        target.unlink()
        outside = self.cwd / "outside.md"
        outside.write_text("do not alter", encoding="utf-8")
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable for this account")
        linked = self.invoke("tasks", "get", "--id", task["id"])
        self.assertNotEqual(linked.returncode, 0)
        self.assertIn("linked storage", linked.stderr)
        self.assertEqual(outside.read_text(encoding="utf-8"), "do not alter")


if __name__ == "__main__":
    unittest.main()
