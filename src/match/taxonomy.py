"""Canonical technology taxonomy + synonym normalization (FR-3.1).

Small, hand-maintained map for the MVP. Grows as real postings reveal synonyms.
Deliberately dependency-free so it can be prompt-cached alongside the master
resume in Bedrock later.
"""
from __future__ import annotations

import re

# canonical -> family
FAMILY: dict[str, str] = {
    "python": "language", "java": "language", "javascript": "language",
    "typescript": "language", "go": "language", "rust": "language",
    "sql": "language",
    "react": "framework", "node": "framework", "django": "framework",
    "fastapi": "framework", "spring": "framework", "flask": "framework",
    "aws": "cloud", "gcp": "cloud", "azure": "cloud",
    "lambda": "cloud", "s3": "cloud", "dynamodb": "cloud", "bedrock": "cloud",
    "postgres": "data", "mysql": "data", "spark": "data", "kafka": "data",
    "airflow": "data", "snowflake": "data",
    "docker": "infra", "kubernetes": "infra", "terraform": "infra",
    "cdk": "infra", "cloudformation": "infra",
    "git": "tooling", "pytest": "tooling", "linux": "tooling",
}

# raw token (lowercased) -> canonical
SYNONYMS: dict[str, str] = {
    "react.js": "react", "reactjs": "react", "react js": "react",
    "node.js": "node", "nodejs": "node",
    "js": "javascript", "ts": "typescript", "golang": "go",
    "postgresql": "postgres", "psql": "postgres",
    "k8s": "kubernetes", "kube": "kubernetes",
    "amazon web services": "aws", "aws lambda": "lambda",
    "apache spark": "spark", "apache kafka": "kafka", "apache airflow": "airflow",
    "gcp cloud": "gcp", "google cloud": "gcp",
    "aws cdk": "cdk",
}

_SPLIT = re.compile(r"[\s/,;()]+")


def normalize_skill(raw: str) -> str:
    """Map a raw skill token to its canonical form (identity if unknown)."""
    t = " ".join(raw.lower().split())
    if t in SYNONYMS:
        return SYNONYMS[t]
    if t in FAMILY:
        return t
    return t


def normalize_skills(raw_skills: list[str]) -> list[str]:
    """Normalize + dedupe, preserving first-seen order."""
    out: list[str] = []
    for raw in raw_skills:
        c = normalize_skill(raw)
        if c and c not in out:
            out.append(c)
    return out


def family_of(canonical: str) -> str:
    return FAMILY.get(canonical, "other")
