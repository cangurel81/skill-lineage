---
name: skill-lineage
description: Detect duplicate, near-duplicate, variant and conflicting SKILL.md files across large skill catalogs. Use when auditing a skills folder, cleaning up copied skills, reviewing translated or renamed variants, resolving name collisions before publishing a skill, or producing a review-only removal plan without deleting anything.
---

# Skill Lineage

Finds copies and collisions in a catalog of `SKILL.md` files and produces an
advisory cleanup plan. It is deterministic, standard-library only, and never
modifies, moves or deletes files.

## When to use

- A skills directory grew through downloads, translations and forks and you
  need to know what is a real duplicate versus a distinct skill.
- Two skills claim the same `name` and you must decide which one is canonical.
- Before publishing a new skill, you want to check whether a near-identical
  one already exists in the catalog.
- You need a machine-readable inventory for a catalog review or CI gate.

## Core concepts

Four layers of evidence, from strictest to loosest:

| Layer | Meaning |
|---|---|
| `exact` | Identical raw bytes (SHA-256 of the file). |
| `normalized` | Same content after sorting frontmatter keys, normalizing line endings and collapsing blank-line runs. |
| `name-variant` | Same name, high token overlap (Jaccard, default `0.85`), different wording/translation. |
| `name-conflict` | Same name, genuinely different content — two skills competing for one identifier. |

A canonical copy is chosen per group with an explicit, explainable score:
complete frontmatter, descriptive text, untranslated body, preferred install
root, and oldest modification time. Every decision is reported with its reason.

## Commands

```
python scripts/skill-lineage.py scan   <root> [root ...] [--json] [--near 0.85] [--fail-on any|conflict|never]
python scripts/skill-lineage.py plan   <root> [root ...] [--json] [--near 0.85] [--fail-on any|conflict|never]
python scripts/skill-lineage.py report <root> [root ...] [--json] [--near 0.85] [--fail-on any|conflict|never]
```

- `scan` — summary of all findings. Start here.
- `plan` — review-only list of `remove-candidate` actions, each with a
  `duplicate_of` target, a confidence level and a `requires_review` flag.
- `report` — a Markdown report with per-group keep/candidate decisions.

A root may be a single `SKILL.md`, a skill directory, or a whole catalog tree.
Multiple roots are scanned in one pass; the same file is counted once.

## Output contract

- `--json` emits one JSON object with `tool`, `version`, `command`, `roots`,
  `near_threshold`, the command payload and `exit_code`.
- Exit `0` = completed, `1` = findings matched `--fail-on`, `2` = bad input or
  an unreadable path. Default `--fail-on never` keeps exploratory runs green.
- Use `--fail-on conflict` in CI to block true name collisions only, or
  `--fail-on any` to block on any copy or variant.

## Review workflow

1. Run `scan --json` and read the summary counts.
2. Run `report` and inspect each group's canonical choice and reason.
3. Run `plan --json` to get candidate paths for a human review queue.
4. Verify each candidate manually, then remove files yourself. This tool
   intentionally has no delete, move or write command.

## Safety

- Plan-only by design: `dry_run: true`, `destructive: false` are always set.
- Translation is treated as a variant, never as an exact duplicate.
- Conservative normalization keeps wording significant, so unrelated skills
  with a shared template header are not merged into one group.
