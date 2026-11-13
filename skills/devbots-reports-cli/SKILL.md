---
name: devbots-reports-cli
description: Create, list, and inspect Devbots project-specific design, implementation, research, and review reports.
---

# Devbots reports CLI

Run this skill's `reports-cli.py` with Python 3.10+ using its absolute installed path.
Read the [workspace manual](../devbots-workspace-cli/SKILL.md) and initialize storage first.
Global `--workspace-path PATH` and `--json` flags go before the subcommand.
Default storage is exactly current-directory `.devbots`; pass the shared absolute workspace path for team work.

## Commands

In examples, `reports-cli.py` means this skill's actual script path.

```bash
echo "Architecture decisions, alternatives, and evidence..." | python reports-cli.py create --title "Architecture" --author Planiel
python reports-cli.py --json list
python reports-cli.py list --show-path
python reports-cli.py get --id abc123
```

* `create --title TITLE --author AUTHOR [--empty]` reads a nonempty Markdown report from stdin, unless `--empty`.
* `list [--show-path]` lists reports by creation time, then ID.
* `get --id ID` returns metadata and full Markdown body.
    * Use the full 16-character lowercase hex ID or an unambiguous prefix.

Human creation prints the absolute report path; JSON creation returns metadata, path, and body.
JSON lists contain metadata and absolute paths; JSON get also includes the body.
No report editing, deletion, or editor-launch command is provided.
Create a follow-up report and reference the earlier ID when revising a decision.

## Reporting process

Write a report for architecture, implementation, research, review, or material coordination decisions.
Use your nickname as author.
Keep scope, decisions, evidence, validation outcomes, limitations, and follow-up work concise.
Review reports should identify affected paths, severity/category, impact, and specific requested changes.
Distinguish unavailable checks from actual passes.
Add the resulting report ID to the task discussion and return it to Chief.
Reports are project-specific; use other authorized session resources for reusable knowledge when appropriate.

## Storage and failures

Records live in `reports/ID.report.md` with JSON frontmatter (ID/title/author/created/updated) and a Markdown body.
Labels support Unicode and colons but must be nonempty and single-line.
Writes use trusted local storage and must be serialized per record.
Exit `0` means success, including an empty list; `1` means storage/input failure; `2` means command syntax error.
Failures go to stderr.
The CLI never accesses the network, evaluates shell code, or opens an editor.
