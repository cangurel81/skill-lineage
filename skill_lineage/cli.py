"""Command line interface for skill-lineage."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Sequence

from . import __version__
from .discover import SkillRecord, discover
from .errors import ToolError
from .fingerprint import Fingerprint, fingerprint
from .group import analyze, build_plan
from .report import render_markdown

FAIL_CHOICES = ("any", "conflict", "never")
COMMANDS = ("scan", "plan", "report")


def _emit_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def _collect(
    roots: Sequence[str], near: float
) -> tuple[List[SkillRecord], List[Fingerprint], Dict[str, Any]]:
    records = discover(roots)
    if not records:
        raise ToolError("no SKILL.md files found under the given roots")
    prints = [fingerprint(record.raw, record.doc) for record in records]
    result = analyze(records, prints, near_threshold=near)
    return records, prints, result


def _should_fail(analysis: Dict[str, Any], mode: str) -> bool:
    if mode == "never":
        return False
    summary = analysis["summary"]
    if mode == "conflict":
        return summary["name_conflicts"] > 0
    if mode == "any":
        return bool(
            summary["exact_copies"]
            or summary["normalized_copies"]
            or summary["name_conflicts"]
            or summary["name_variants"]
        )
    return False


def _base_payload(command: str, roots: Sequence[str], near: float) -> Dict[str, Any]:
    return {
        "tool": "skill-lineage",
        "version": __version__,
        "command": command,
        "roots": list(roots),
        "near_threshold": near,
    }


def _print_summary(analysis: Dict[str, Any]) -> None:
    s = analysis["summary"]
    print("Skills scanned:            %d" % s["skills"])
    print("Exact duplicate groups:    %d" % s["exact_groups"])
    print("Exact copies:              %d" % s["exact_copies"])
    print("Normalized groups:         %d" % s["normalized_groups"])
    print("Normalized copies:         %d" % s["normalized_copies"])
    print("Name variants:             %d" % s["name_variants"])
    print("Name conflicts:            %d" % s["name_conflicts"])
    print("Removal candidates:        %d" % s["remove_candidates"])


def _print_plan(plan: Dict[str, Any]) -> None:
    print("Dry run: %s | destructive: %s" % (plan["dry_run"], plan["destructive"]))
    print("Removal candidates: %d" % len(plan["actions"]))
    for action in plan["actions"]:
        print(
            "[%s] %s -> keep %s"
            % (action["confidence"], action["path"], action["duplicate_of"])
        )
    if not plan["actions"]:
        print("No cleanup candidates found.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-lineage",
        description="Deterministic duplicate and conflict detection for SKILL.md catalogs.",
    )
    sub = parser.add_subparsers(dest="command")
    for name in COMMANDS:
        child = sub.add_parser(
            name,
            help={
                "scan": "analyze a catalog and print a summary",
                "plan": "emit a review-only cleanup plan",
                "report": "render a Markdown report",
            }[name],
        )
        child.add_argument("roots", nargs="+", help="skill files, dirs or catalog roots")
        child.add_argument(
            "--near",
            type=float,
            default=0.85,
            help="token Jaccard threshold for name variants (default: 0.85)",
        )
        child.add_argument("--json", action="store_true", help="emit machine-readable JSON")
        child.add_argument(
            "--fail-on",
            choices=FAIL_CHOICES,
            default="never",
            help="exit 1 when findings match (default: never)",
        )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command not in COMMANDS:
        parser.print_help()
        return 2

    if not 0.0 <= args.near <= 1.0:
        print("error: --near must be between 0.0 and 1.0", file=sys.stderr)
        return 2

    try:
        _records, _prints, analysis = _collect(args.roots, args.near)
    except ToolError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    except OSError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2

    exit_code = 1 if _should_fail(analysis, args.fail_on) else 0

    if args.command == "plan":
        plan = build_plan(analysis)
        if args.json:
            payload = _base_payload("plan", args.roots, args.near)
            payload["plan"] = plan
            payload["exit_code"] = exit_code
            _emit_json(payload)
        else:
            _print_plan(plan)
        return exit_code

    if args.command == "report":
        if args.json:
            payload = _base_payload("report", args.roots, args.near)
            payload["analysis"] = analysis
            payload["exit_code"] = exit_code
            _emit_json(payload)
        else:
            print(render_markdown(analysis, args.roots))
        return exit_code

    if args.json:
        payload = _base_payload("scan", args.roots, args.near)
        payload["analysis"] = analysis
        payload["exit_code"] = exit_code
        _emit_json(payload)
    else:
        _print_summary(analysis)
    return exit_code
