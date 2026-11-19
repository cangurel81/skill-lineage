"""Discover SKILL.md files and attach lightweight source metadata."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

from .frontmatter import SkillDoc, parse

SKILL_FILE = "SKILL.md"
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}

CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")

_ROOT_LABELS = (
    ("local-skills", "local"),
    ("claude-seo", "claude-seo"),
    (".claude/skills", "claude"),
    ("opencode/skills", "opencode"),
    ("/vendor", "vendor"),
)


@dataclass(frozen=True)
class SkillRecord:
    """One discovered skill with the data needed for lineage decisions."""

    path: str
    skill_file: str
    name: str
    dir_name: str
    root: str
    root_label: str
    size: int
    mtime: float
    raw: bytes
    doc: SkillDoc

    @property
    def description(self) -> str:
        value = self.doc.get("description")
        return value.strip() if isinstance(value, str) else ""

    @property
    def translated(self) -> bool:
        sample = self.doc.body[:2000]
        return bool(CJK_PATTERN.search(sample))


def root_label(path: os.PathLike) -> str:
    """Classify a root into a stable short label for reports."""
    lowered = Path(path).expanduser().as_posix().lower()
    for needle, label in _ROOT_LABELS:
        if needle in lowered:
            return label
    return "custom"


def _read(path: Path) -> SkillRecord:
    data = path.read_bytes()
    doc = parse(data.decode("utf-8-sig", errors="replace"), path.as_posix())
    doc.bom = data.startswith(b"\xef\xbb\xbf")
    parent = path.parent
    name = doc.get("name")
    if not isinstance(name, str) or not name.strip():
        name = parent.name
    stat = path.stat()
    root = str(parent)
    return SkillRecord(
        path=parent.as_posix(),
        skill_file=path.as_posix(),
        name=name.strip(),
        dir_name=parent.name,
        root=root,
        root_label=root_label(root),
        size=len(data),
        mtime=stat.st_mtime,
        raw=data,
        doc=doc,
    )


def discover(paths: Sequence[os.PathLike]) -> List[SkillRecord]:
    """Discover skills from files, skill dirs or trees; preserve input order."""
    found: List[SkillRecord] = []
    seen = set()
    for entry in paths:
        target = Path(entry).expanduser()
        candidates: List[Path] = []
        if target.is_file():
            candidates = [target] if target.name == SKILL_FILE else []
        elif target.is_dir():
            if (target / SKILL_FILE).is_file():
                candidates = [target / SKILL_FILE]
            else:
                for root, dirs, files in os.walk(str(target)):
                    dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
                    if SKILL_FILE in files:
                        candidates.append(Path(root) / SKILL_FILE)
        for candidate in sorted(candidates):
            key = str(candidate.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(_read(candidate))
    return found
