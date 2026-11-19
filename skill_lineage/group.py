"""Group discovered skills into duplicates, variants and name conflicts."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Sequence

from .discover import SkillRecord
from .fingerprint import Fingerprint, jaccard

_PREFERRED_ROOTS = {"local", "claude", "opencode"}


def _score(record: SkillRecord, oldest_mtime: float) -> int:
    score = 0
    if record.name and record.description:
        score += 3
    if len(record.description) >= 25:
        score += 2
    if not record.translated:
        score += 2
    if record.root_label in _PREFERRED_ROOTS:
        score += 1
    if record.root_label == "vendor":
        score -= 1
    if record.mtime == oldest_mtime:
        score += 1
    return score


def _reason(record: SkillRecord, oldest_mtime: float) -> str:
    bits = []
    if record.name and record.description:
        bits.append("complete frontmatter")
    if not record.translated:
        bits.append("untranslated")
    if record.root_label in _PREFERRED_ROOTS:
        bits.append("preferred root: " + record.root_label)
    if record.mtime == oldest_mtime:
        bits.append("oldest file in group")
    return "; ".join(bits) or "lowest sort order"


def _member(index: int, record: SkillRecord, score: int, reason: str) -> Dict[str, Any]:
    return {
        "index": index,
        "path": record.path,
        "root": record.root_label,
        "name": record.name,
        "size": record.size,
        "score": score,
        "keep_reason": reason,
    }


def _make_group(
    kind: str,
    key: str,
    indexes: List[int],
    records: Sequence[SkillRecord],
) -> Dict[str, Any]:
    oldest = min(records[i].mtime for i in indexes)
    ranked = []
    for index in indexes:
        record = records[index]
        score = _score(record, oldest)
        ranked.append(
            (
                -score,
                len(record.path),
                record.path,
                index,
                _member(index, record, score, _reason(record, oldest)),
            )
        )
    ranked.sort()
    canonical = ranked[0][4]
    members = [item[4] for item in ranked]
    return {
        "kind": kind,
        "key": key,
        "canonical": canonical["path"],
        "canonical_reason": canonical["keep_reason"],
        "members": members,
        "candidates": [item["path"] for item in members[1:]],
    }


def analyze(
    records: Sequence[SkillRecord],
    fingerprints: Sequence[Fingerprint],
    near_threshold: float = 0.85,
) -> Dict[str, Any]:
    """Build duplicate/variant/conflict groups. Pure and deterministic."""
    by_exact: Dict[str, List[int]] = defaultdict(list)
    by_normalized: Dict[str, List[int]] = defaultdict(list)
    by_name: Dict[str, List[int]] = defaultdict(list)

    for index, (record, fp) in enumerate(zip(records, fingerprints)):
        by_exact[fp.exact].append(index)
        by_normalized[fp.normalized].append(index)
        by_name[record.name.lower()].append(index)

    exact_groups = [
        _make_group("exact", key, members, records)
        for key, members in sorted(by_exact.items())
        if len(members) > 1
    ]

    normalized_groups = []
    for key, members in sorted(by_normalized.items()):
        if len(members) < 2:
            continue
        if len({fingerprints[i].exact for i in members}) == 1:
            continue  # already reported as an exact group
        normalized_groups.append(_make_group("normalized", key, members, records))

    conflicts: List[Dict[str, Any]] = []
    variants: List[Dict[str, Any]] = []
    for key, members in sorted(by_name.items()):
        if len(members) < 2:
            continue
        hashes = {fingerprints[i].normalized for i in members}
        if len(hashes) == 1:
            continue  # same content under one name: already an exact/normalized group
        similar = any(
            jaccard(fingerprints[left].tokens, fingerprints[right].tokens) >= near_threshold
            for pos, left in enumerate(members)
            for right in members[pos + 1 :]
        )
        group = _make_group(
            "name-variant" if similar else "name-conflict", key, members, records
        )
        (variants if similar else conflicts).append(group)

    summary = {
        "skills": len(records),
        "exact_groups": len(exact_groups),
        "exact_copies": sum(len(group["candidates"]) for group in exact_groups),
        "normalized_groups": len(normalized_groups),
        "normalized_copies": sum(len(group["candidates"]) for group in normalized_groups),
        "name_conflicts": len(conflicts),
        "name_variants": len(variants),
        "remove_candidates": sum(
            len(group["candidates"])
            for group in exact_groups + normalized_groups + conflicts + variants
        ),
    }
    return {
        "summary": summary,
        "exact": exact_groups,
        "normalized": normalized_groups,
        "conflicts": conflicts,
        "variants": variants,
    }


def build_plan(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Return a review-only cleanup plan. Never deletes or mutates files."""
    actions: List[Dict[str, Any]] = []
    for group in analysis["exact"]:
        for path in group["candidates"]:
            actions.append(
                {
                    "action": "remove-candidate",
                    "path": path,
                    "duplicate_of": group["canonical"],
                    "confidence": "exact",
                    "requires_review": False,
                }
            )
    for kind, groups in (
        ("normalized", analysis["normalized"]),
        ("name-variant", analysis["variants"]),
        ("name-conflict", analysis["conflicts"]),
    ):
        for group in groups:
            for path in group["candidates"]:
                actions.append(
                    {
                        "action": "remove-candidate",
                        "path": path,
                        "duplicate_of": group["canonical"],
                        "confidence": kind,
                        "requires_review": True,
                    }
                )
    actions.sort(key=lambda item: (item["path"], item["confidence"]))
    return {
        "dry_run": True,
        "destructive": False,
        "actions": actions,
        "summary": analysis["summary"],
    }
