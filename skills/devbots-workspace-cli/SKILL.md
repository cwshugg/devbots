---
name: devbots-workspace-cli
description: Initialize, inspect, and name the trusted local Devbots collaboration workspace.
---

# Devbots workspace CLI

Run the bundled `workspace-cli.py` with Python 3.10+ using its absolute installed path.
The shared module is resolved relative to the script, never the current directory.
No packages, editor launches, or network access are required.

## Commands

In examples, `workspace-cli.py` means this skill's actual script path.

```bash
python workspace-cli.py init --name "My project"
python workspace-cli.py --json show
python workspace-cli.py --workspace-path "/path/to/.devbots" config --name "New name"
python workspace-cli.py --workspace-path "/path/to/.devbots" config
```

* `init [--name NAME]` creates the workspace, config, `tasks/`, `reports/`, and `scratch/`.
    * The initial name defaults to the workspace parent's directory name.
    * Reinitialization preserves existing configuration and records.
    * A different name on reinitialization is rejected; use `config --name`.
* `show` returns the workspace and config paths, current config, and fixed task statuses.
* `config [--name NAME]` reads config or changes only its display name.

Global options precede the subcommand:

* `--workspace-path PATH` selects the workspace **itself**, defaulting to current-directory `.devbots`.
* `--json` emits a single prompt-free JSON object.

There is no ancestor search or Git-root fallback.
Pass the resulting absolute workspace path to every teammate and every CLI invocation.
Read commands require initialization and have no write side effects.

## Collaboration defaults

Coordinate with humans and teammates toward high-quality software and documentation; share concise progress, decisions, and blockers.
Keep Git interactions local unless remote access is explicitly authorized, and commit only when explicitly asked; leave review and publication to the human.
Initialize shared storage before creating durable task or report records; reserve `scratch/` for working artifacts.

## Storage contract

`devbots-config.json` contains exactly `{"name": "..."}`.
Unknown fields are rejected without rewriting the file; there is no automatic conversion.
Task statuses are `pending`, `underway`, `done`, and `abandoned`, not configurable.
`init` creates only `workspace/.gitignore` with `*` and a final newline.
An identical ignore file is preserved; any conflicting existing contents fail before initialization writes.
Project and parent ignore files are never edited.

Storage must be trusted, local, and user-owned.
Traversal components, linked components, and filesystem-root workspaces are rejected.
Chief must serialize conflicting record mutations; there is no multiwriter guarantee.
Use `scratch/TASK_ID/` for temporary research and implementation artifacts.
The tools never automatically execute workspace contents.

## Results

Both human and JSON modes show configuration and absolute paths.
Exit `0` means success, `1` means input/storage failure, and `2` means command syntax error.
Failures are printed to stderr, not mixed into JSON stdout.
