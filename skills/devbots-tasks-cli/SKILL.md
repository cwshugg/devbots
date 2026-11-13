---
name: devbots-tasks-cli
description: Track Devbots task ownership, status, directed links, and timestamped discussions in local storage.
---

# Devbots tasks CLI

Run this skill's `tasks-cli.py` with Python 3.10+ using its absolute installed path.
Read the [workspace manual](../devbots-workspace-cli/SKILL.md) and initialize storage first.
Global `--workspace-path PATH` and `--json` flags go before the subcommand.
Default storage is exactly current-directory `.devbots`; assignments should always pass the shared absolute workspace path.

## Commands

In examples, `tasks-cli.py` means this skill's actual script path.
Replace example IDs with IDs returned by `create`.

```bash
echo "Implement the approved design" | python tasks-cli.py create --title "Feature" --author Chief --owner Byteboy
python tasks-cli.py --json list --status underway --owner Byteboy
python tasks-cli.py get --id abc123
python tasks-cli.py set-status --id abc123 --status underway
python tasks-cli.py set-owner --id abc123 --owner Scribs
echo "Tests pass; report ID is ..." | python tasks-cli.py add-discussion --id abc123 --author Byteboy
python tasks-cli.py add-link --id abc123 --link-id def456
python tasks-cli.py remove-link --id abc123 --link-id def456
```

* `create --title TITLE --author AUTHOR [--status STATUS] [--owner OWNER] [--linked-tasks ID,ID] [--empty]` reads a nonempty Markdown description from stdin, unless `--empty`.
    * Status defaults to `pending`.
    * Linked tasks must already exist and resolve uniquely.
* `list [--status STATUS] [--owner OWNER] [--show-path]` lists records by creation time, then ID.
    * Owner filtering is exact and case-sensitive.
* `get --id ID` returns all metadata, discussions, and the Markdown description.
* `set-status --id ID --status STATUS` accepts only `pending`, `underway`, `done`, or `abandoned`.
* `set-owner --id ID --owner OWNER` updates ownership; `--owner ""` clears it.
* `add-discussion --id ID --author AUTHOR` reads a nonempty Markdown update from stdin and records author and UTC time.
    * Appends `## TIMESTAMP - AUTHOR`, a blank line, and the exact Markdown input at the bottom of the task.
* `add-link --id ID --link-id ID` adds a directed link to an existing task, without duplicates.
* `remove-link --id ID --link-id ID` removes an existing directed link.
    * Self-links and missing links are errors.

All ID operands accept full 16-character lowercase hex IDs or unambiguous prefixes.
Links store full IDs and are organizational references, not an automatic dependency scheduler.
There is no delete command or automatic editor launch.

## Team workflow

Find or create a task before work; use your nickname as author and owner.
Work on one assigned task at a time, set it `underway`, and record progress and handoff report IDs in discussions.
Chief assigns specialists and serializes conflicting updates.
Mark `done` only when the assigned acceptance criteria are met; use `abandoned` rather than deleting cancelled work.
Create and link discovered follow-up work when necessary.

## Storage and output

Records live in `tasks/ID.task.md` with JSON frontmatter and Markdown sections.
Frontmatter includes ID, title, author, owner, status, created/updated UTC times, and `linked_tasks`, but **never `discussions`**.
The first section is the exact description; subsequent sections contain `## TIMESTAMP - AUTHOR`, a blank line, and the discussion body.
Each section is preceded by `<!-- devbots-section: N -->` and a newline, then followed by two separator newlines.
`N` counts Unicode characters in that section, excluding the marker and separator.
These CLI-maintained HTML comments keep arbitrary Markdown, matching headings/markers, whitespace, and repeated entries lossless.
Timestamps use UTC ISO format with six fractional digits and `+00:00`; authors cannot contain line breaks or control characters.
Do not hand-edit section lengths. Unsupported old frontmatter discussions or malformed framing are rejected without rewriting; no conversion is performed.
JSON labels support colons and Unicode; labels must be nonempty and single-line.
Create prints the absolute record path in human mode; list prints concise rows.
`--json` returns complete metadata, computed `discussions` objects containing author/created/body, and absolute paths (plus the description as `body` for create/get/mutations).
Human `get` displays the description followed by discussion headings and Markdown bodies.
Empty lists succeed.
Malformed records, ambiguous IDs, unsafe paths, and failed mutations return `1`; command syntax errors return `2`.
No runtime network, shell evaluation, or editor invocation is performed.
