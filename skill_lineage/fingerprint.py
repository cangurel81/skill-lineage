"""Deterministic content fingerprints for SKILL.md files."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import FrozenSet

from .frontmatter import SkillDoc

_WORD_PATTERN = re.compile(r"[a-z0-9_-]{3,}")


@dataclass(frozen=True)
class Fingerprint:
    exact: str
    normalized: str
    tokens: FrozenSet[str]


def normalize(doc: SkillDoc) -> str:
    """Normalize field order, line endings and blank-run noise.

    Deliberately conservative: wording and translation stay significant, so a
    translated copy is a variant rather than a false duplicate.
    """
    fields = json.dumps(doc.fields, sort_keys=True, ensure_ascii=False, default=str)
    lines = []
    blank_run = 0
    for line in (doc.body or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = line.rstrip()
        if not cleaned:
            blank_run += 1
            if blank_run > 2:
                continue
        else:
            blank_run = 0
        lines.append(cleaned)
    return fields + "\n---\n" + "\n".join(lines).strip() + "\n"


def tokens(doc: SkillDoc) -> FrozenSet[str]:
    text = normalize(doc).lower()
    return frozenset(_WORD_PATTERN.findall(text))


def fingerprint(raw: bytes, doc: SkillDoc) -> Fingerprint:
    return Fingerprint(
        exact=hashlib.sha256(raw).hexdigest(),
        normalized=hashlib.sha256(normalize(doc).encode("utf-8")).hexdigest(),
        tokens=tokens(doc),
    )


def jaccard(left: FrozenSet[str], right: FrozenSet[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)
