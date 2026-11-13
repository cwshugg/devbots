"""Local Devbots collaboration workflows (GPL-3.0-only).

See https://www.gnu.org/licenses/gpl-3.0.html for license terms.
Only the standard library is needed; storage is trusted and single-writer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("pending", "underway", "done", "abandoned")
KINDS = {"tasks": "task", "reports": "report"}
IGNORE = "*\n"


def now() -> str:
    """Return a sortable UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def safe_path(path: Path) -> Path:
    """Reject traversal and linked components before accessing local storage."""
    if ".." in path.parts or (os.name != "nt" and "\\" in str(path)):
        raise ValueError("unsafe path: traversal or foreign path separators")
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        # Reparse attributes also catch Windows junctions on Python 3.10,
        # which predates Path.is_junction().
        if component.is_symlink() or (
            os.name == "nt"
            and component.exists()
            and component.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError(f"linked storage paths are not supported: {component}")
    return absolute


def workspace_path(value: str | None) -> Path:
    """Select exactly the supplied workspace or cwd/.devbots; never search."""
    path = safe_path(Path(value) if value else Path.cwd() / ".devbots")
    if path == Path(path.anchor):
        raise ValueError("the filesystem root cannot be a workspace")
    return path


def read_config(workspace: Path) -> dict[str, Any]:
    """Read the workspace display name without discarding unknown fields."""
    path = safe_path(workspace / "devbots-config.json")
    config = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(config, dict)
        or not isinstance(config.get("name"), str)
        or set(config) != {"name"}
    ):
        raise ValueError(
            "invalid devbots-config.json (expected only name); file preserved"
        )
    label(config["name"])
    return config


def write_text(path: Path, text: str, *, create: bool = False) -> None:
    """Create exclusively or atomically replace a validated local file."""
    safe_path(path)
    if create:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        return
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=".devbots-",
            delete=False,
        ) as stream:
            temp_name = stream.name
            stream.write(text)
        os.replace(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            Path(temp_name).unlink()


def json_text(value: Any) -> str:
    """Encode readable UTF-8 JSON with a final newline."""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def label(value: str) -> str:
    """Validate a nonempty, single-line metadata label."""
    if not value.strip() or any(ord(char) < 32 for char in value):
        raise ValueError("metadata labels must be nonempty single-line text")
    return value.strip()


def body_input(empty: bool = False) -> str:
    """Read explicit UTF-8 Markdown from stdin without interactive prompts."""
    body = "" if empty else sys.stdin.read()
    if not empty and not body.strip():
        raise ValueError("provide nonempty Markdown on stdin (or use --empty)")
    return body


def discussion_heading(discussion: dict) -> str:
    """Validate discussion labels and produce a visible Markdown heading."""
    author = label(discussion["author"])
    if author != discussion["author"] or any(
        char in author for char in "\x7f\x85\u2028\u2029"
    ):
        raise ValueError("discussion author must be nonempty single-line text")
    timestamp = discussion["created"]
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00", timestamp):
        raise ValueError("discussion timestamp must be a UTC ISO timestamp")
    datetime.fromisoformat(timestamp)
    if not discussion["body"].strip():
        raise ValueError("discussion body must be nonempty Markdown")
    return f"## {timestamp} - {author}"


def task_markdown(body: str, discussions: list[dict]) -> str:
    """Frame Markdown sections by character length, not Markdown delimiters."""
    sections = [body]
    for discussion in discussions:
        sections.append(discussion_heading(discussion) + "\n\n" + discussion["body"])
    return "".join(
        f"<!-- devbots-section: {len(section)} -->\n{section}\n\n"
        for section in sections
    )


def read_task_markdown(content: str) -> tuple[str, list[dict]]:
    """Read exact-length sections so user headings/fences cannot split entries."""
    sections = []
    position = 0
    while position < len(content):
        marker = re.match(
            r"<!-- devbots-section: (0|[1-9][0-9]*) -->\n", content[position:]
        )
        if not marker:
            raise ValueError("invalid task Markdown framing; file preserved")
        start = position + marker.end()
        end = start + int(marker[1])
        if content[end : end + 2] != "\n\n":
            raise ValueError("invalid task Markdown section length; file preserved")
        sections.append(content[start:end])
        position = end + 2
    if not sections:
        raise ValueError("missing task description section; file preserved")
    discussions = []
    for section in sections[1:]:
        heading, separator, body = section.partition("\n\n")
        match = re.fullmatch(r"## (\S+) - (.+)", heading)
        if not separator or not match:
            raise ValueError("invalid task discussion heading; file preserved")
        discussion = {"created": match[1], "author": match[2], "body": body}
        discussion_heading(discussion)
        discussions.append(discussion)
    return sections[0], discussions


def record_path(workspace: Path, kind: str, record_id: str) -> Path:
    """Construct a record path only from a full validated ID."""
    if not re.fullmatch(r"[a-f0-9]{16}", record_id):
        raise ValueError("invalid record ID")
    return safe_path(workspace / kind / f"{record_id}.{KINDS[kind]}.md")


def read_record(path: Path, kind: str) -> tuple[dict[str, Any], str]:
    """Read JSON-frontmatter Markdown; reject malformed records, never skip."""
    with safe_path(path).open(
        encoding="utf-8", newline="" if kind == "tasks" else None
    ) as stream:
        content = stream.read()
    parts = content.split("\n---\n", 1)
    if not content.startswith("---\n") or len(parts) != 2:
        raise ValueError(f"missing JSON frontmatter: {path}")
    metadata = json.loads(parts[0][4:])
    if not isinstance(metadata, dict):
        raise TypeError(f"invalid metadata: {path}")
    for key in ("id", "title", "author", "created", "updated"):
        if not isinstance(metadata.get(key), str):
            raise TypeError(f"invalid {key}: {path}")
        label(metadata[key])
    if (
        not re.fullmatch(r"[a-f0-9]{16}", metadata["id"])
        or path.name != f"{metadata['id']}.{KINDS[kind]}.md"
    ):
        raise ValueError(f"record ID/filename mismatch: {path}")
    if kind == "tasks":
        if "discussions" in metadata:
            raise ValueError(
                f"task discussions must be Markdown, not frontmatter: {path}; "
                "file preserved; automatic conversion is not supported"
            )
        if (
            metadata.get("status") not in STATUSES
            or not isinstance(metadata.get("owner"), str)
            or not isinstance(metadata.get("linked_tasks"), list)
            or any(
                not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{16}", item)
                for item in metadata["linked_tasks"]
            )
        ):
            raise ValueError(f"invalid task fields: {path}")
        if not parts[1].startswith("\n"):
            raise ValueError(f"missing blank line after task frontmatter: {path}")
        body, metadata["discussions"] = read_task_markdown(parts[1][1:])
        return metadata, body
    return metadata, parts[1].strip()


def records(workspace: Path, kind: str) -> list[tuple[Path, dict, str]]:
    """Load records sorted by creation time and ID."""
    directory = safe_path(workspace / kind)
    if not directory.is_dir():
        raise ValueError(f"missing {kind} directory; run workspace init")
    result = [
        (path, *read_record(path, kind))
        for path in directory.glob(f"*.{KINDS[kind]}.md")
    ]
    return sorted(result, key=lambda row: (row[1]["created"], row[1]["id"]))


def resolve(workspace: Path, kind: str, prefix: str) -> tuple[Path, dict, str]:
    """Resolve an exact ID or unique hex prefix; never treat IDs as paths."""
    if not re.fullmatch(r"[a-f0-9]{1,16}", prefix):
        raise ValueError("IDs must be 1–16 lowercase hexadecimal characters")
    matches = [
        row for row in records(workspace, kind) if row[1]["id"].startswith(prefix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"ID {prefix}: not found or ambiguous ({len(matches)} matches)"
        )
    return matches[0]


def save(path: Path, metadata: dict, body: str, *, create: bool = False) -> dict:
    """Persist JSON metadata and Markdown, returning a machine-readable view."""
    stored = dict(metadata)
    if "discussions" in stored:
        markdown = task_markdown(body, stored.pop("discussions"))
    else:
        body = body.strip()
        markdown = body + "\n"
    write_text(
        path,
        "---\n" + json_text(stored) + "---\n\n" + markdown,
        create=create,
    )
    return {"path": str(path), **metadata, "body": body}


def workspace_command(args: argparse.Namespace, workspace: Path) -> dict:
    """Initialize, inspect, or rename a workspace without editing project files."""
    if args.command == "init":
        config_path = safe_path(workspace / "devbots-config.json")
        ignore_path = safe_path(workspace / ".gitignore")
        # Preflight conflicts before creating any files.
        if ignore_path.exists() and ignore_path.read_text(encoding="utf-8") != IGNORE:
            raise ValueError("workspace/.gitignore conflicts; existing file preserved")
        if config_path.exists():
            config = read_config(workspace)
            if args.name is not None and config["name"] != label(args.name):
                raise ValueError("workspace already named; use config --name")
        else:
            config = {"name": label(args.name or workspace.parent.name)}
        for directory in ("tasks", "reports", "scratch"):
            path = safe_path(workspace / directory)
            if path.exists() and not path.is_dir():
                raise ValueError(f"workspace directory conflicts with file: {path}")
        workspace.mkdir(parents=True, exist_ok=True)
        for directory in ("tasks", "reports", "scratch"):
            (workspace / directory).mkdir(exist_ok=True)
        if not ignore_path.exists():
            write_text(ignore_path, IGNORE, create=True)
        if not config_path.exists():
            write_text(config_path, json_text(config), create=True)
    else:
        config = read_config(workspace)
        if args.command == "config" and args.name is not None:
            config["name"] = label(args.name)
            write_text(workspace / "devbots-config.json", json_text(config))
    return {
        "workspace": str(workspace),
        "config_path": str(workspace / "devbots-config.json"),
        "config": config,
        "task_statuses": list(STATUSES),
    }


def create_record(args: argparse.Namespace, workspace: Path, kind: str) -> dict:
    """Create a task or report with shared metadata."""
    metadata = {
        "id": secrets.token_hex(8),
        "title": label(args.title),
        "author": label(args.author),
        "created": now(),
    }
    metadata["updated"] = metadata["created"]
    if kind == "tasks":
        linked = [
            resolve(workspace, kind, value.strip())[1]["id"]
            for value in args.linked_tasks.split(",")
            if value.strip()
        ]
        metadata.update(
            status=args.status,
            owner=label(args.owner) if args.owner else "",
            linked_tasks=list(dict.fromkeys(linked)),
            discussions=[],
        )
    # Validate the directory before consuming stdin or creating anything.
    directory = safe_path(workspace / kind)
    if not directory.is_dir():
        raise ValueError(f"missing {kind} directory; run workspace init")
    body = body_input(args.empty)
    return save(
        record_path(workspace, kind, metadata["id"]),
        metadata,
        body,
        create=True,
    )


def record_command(args: argparse.Namespace, workspace: Path, kind: str) -> Any:
    """Execute the collaboration commands shared by the thin skill launchers."""
    read_config(workspace)
    if args.command == "create":
        return create_record(args, workspace, kind)
    if args.command == "list":
        rows = records(workspace, kind)
        result = []
        for path, metadata, _ in rows:
            if getattr(args, "status", None) and metadata["status"] != args.status:
                continue
            if (
                getattr(args, "owner", None) is not None
                and metadata["owner"] != args.owner
            ):
                continue
            result.append({"path": str(path), **metadata})
        return result
    path, metadata, body = resolve(workspace, kind, args.id)
    if args.command == "get":
        return {"path": str(path), **metadata, "body": body}
    if args.command == "set-status":
        metadata["status"] = args.status
    elif args.command == "set-owner":
        metadata["owner"] = label(args.owner) if args.owner else ""
    elif args.command == "add-discussion":
        metadata["discussions"].append(
            {
                "author": label(args.author),
                "created": now(),
                "body": body_input(),
            }
        )
    elif args.command in {"add-link", "remove-link"}:
        linked_id = resolve(workspace, kind, args.link_id)[1]["id"]
        if linked_id == metadata["id"]:
            raise ValueError("a task cannot link to itself")
        linked = metadata["linked_tasks"]
        if args.command == "add-link" and linked_id not in linked:
            linked.append(linked_id)
        elif args.command == "remove-link":
            if linked_id not in linked:
                raise ValueError("task link does not exist")
            linked.remove(linked_id)
    metadata["updated"] = now()
    return save(path, metadata, body)


def build_parser(tool: str) -> argparse.ArgumentParser:
    """Build the small source-inspired command-line interface."""
    parser = argparse.ArgumentParser(description=f"Devbots {tool} CLI (Python 3.10+)")
    parser.add_argument(
        "--workspace-path", help="Workspace itself; default cwd/.devbots"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only on stdout")
    commands = parser.add_subparsers(dest="command", required=True)
    if tool == "workspace":
        for command in ("init", "show", "config"):
            sub = commands.add_parser(command)
            if command != "show":
                sub.add_argument("--name", help="Set workspace display name")
        return parser
    create = commands.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--author", required=True)
    create.add_argument("--empty", action="store_true", help="Skip stdin")
    listing = commands.add_parser("list")
    listing.add_argument("--show-path", action="store_true")
    get = commands.add_parser("get")
    get.add_argument("--id", required=True)
    if tool == "tasks":
        create.add_argument("--status", choices=STATUSES, default="pending")
        create.add_argument("--owner", default="")
        create.add_argument("--linked-tasks", default="")
        listing.add_argument("--status", choices=STATUSES)
        listing.add_argument("--owner")
        for command, option in (
            ("set-status", "status"),
            ("set-owner", "owner"),
            ("add-discussion", "author"),
            ("add-link", "link-id"),
            ("remove-link", "link-id"),
        ):
            sub = commands.add_parser(command)
            sub.add_argument("--id", required=True)
            kwargs = {"choices": STATUSES} if option == "status" else {}
            sub.add_argument(f"--{option}", required=True, **kwargs)
    return parser


def emit(value: Any, args: argparse.Namespace) -> None:
    """Render JSON for automation or concise human-readable command results."""
    if args.json:
        print(json_text(value), end="")
    elif args.command == "create":
        print(value["path"])
    elif isinstance(value, list):
        for row in value:
            suffix = f" {row['path']}" if args.show_path else ""
            details = row.get("status", row["author"])
            print(
                f"[{row['id']}] [{row['created']}] {row['title']} ({details}){suffix}"
            )
    elif args.command == "get":
        print(
            json_text(
                {
                    key: val
                    for key, val in value.items()
                    if key not in {"body", "discussions"}
                }
            )
        )
        print(value["body"])
        for discussion in value.get("discussions", []):
            print("\n" + discussion_heading(discussion) + "\n")
            print(discussion["body"])
    else:
        print(json_text(value), end="")


def main(tool: str) -> int:
    """Configure UTF-8 streams and run a skill with concise failures on stderr."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(
                encoding="utf-8", **({"newline": ""} if stream is sys.stdin else {})
            )
    parser = build_parser(tool)
    args = parser.parse_args()
    try:
        workspace = workspace_path(args.workspace_path)
        value = (
            workspace_command(args, workspace)
            if tool == "workspace"
            else record_command(args, workspace, tool)
        )
        emit(value, args)
        return 0
    except (OSError, ValueError, TypeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
