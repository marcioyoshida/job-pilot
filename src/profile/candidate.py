"""CandidateProfile — the candidate's master resume + normalized skills.

Used by Stage 3 (fit) now and Stage 4 (tailoring) later. `master_bullets`
carries stable ids so tailored resume highlights can be traced back to a real
bullet (CON-4, NFR-3) — nothing gets invented downstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.match.taxonomy import normalize_skills


@dataclass
class MasterBullet:
    id: str
    text: str
    skills: list[str] = field(default_factory=list)


@dataclass
class CandidateProfile:
    name: str = ""
    headline: str = ""
    skills: list[str] = field(default_factory=list)
    master_bullets: list[MasterBullet] = field(default_factory=list)
    prefs: dict[str, Any] = field(default_factory=dict)

    def normalized_skills(self) -> list[str]:
        """Canonical skill set: declared skills + any skills tagged on bullets."""
        raw = list(self.skills)
        for b in self.master_bullets:
            raw.extend(b.skills)
        return normalize_skills(raw)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CandidateProfile":
        d = d or {}
        bullets = [
            MasterBullet(id=str(b.get("id", i)), text=b.get("text", ""),
                         skills=b.get("skills", []))
            for i, b in enumerate(d.get("master_bullets", []))
        ]
        return cls(
            name=d.get("name", ""),
            headline=d.get("headline", ""),
            skills=d.get("skills", []),
            master_bullets=bullets,
            prefs=d.get("prefs", {}),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CandidateProfile":
        import yaml

        return cls.from_dict(yaml.safe_load(Path(path).read_text()))
