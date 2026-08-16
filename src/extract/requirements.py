"""Stage 2 — extract structured Requirements from a JD (FR-2.1/2.2/2.3).

Two extractors behind one interface:

- HeuristicExtractor (default): deterministic, offline, free. Scans the JD
  against the canonical skill taxonomy and a few regexes. It CANNOT fabricate —
  it only reports what literally appears in the JD, and stores the surrounding
  text as evidence (NFR-3). It leaves fields it can't reliably detect as
  None/empty rather than guessing (certifications, comp, screening questions,
  responsibilities, domain, languages).
- BedrockExtractor (seam): LLM-assisted for higher recall/structure, following
  the house model-tiering (cheap model, batch, prompt-cache). Guarded behind
  ONCA-style env flags; raises NotImplementedError until Phase P2-LLM.

`extract_requirements(posting)` uses the heuristic extractor by default.
"""
from __future__ import annotations

import re
from typing import Optional, Protocol

from src.ingest.base import Posting, Requirements
from src.match.taxonomy import normalize_skill, recognizable_tokens

# --- marker phrases for must-have vs nice-to-have sections -------------------
_MUST_MARKERS = [
    "requirements", "required", "must have", "must-have", "qualifications",
    "what you'll need", "what you will need", "you have", "minimum",
    "we're looking for", "we are looking for", "basic qualifications",
]
_NICE_MARKERS = [
    "nice to have", "nice-to-have", "preferred", "bonus", "a plus",
    "good to have", "pluses", "nice if", "preferred qualifications",
    "desirable",
]

_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs|anos)\b", re.I)
_REMOTE = re.compile(r"\b(remote|hybrid|on-?site|in-?office)\b", re.I)
_EDU = re.compile(
    r"(ph\.?d|master'?s|master of|bachelor'?s?|b\.?s\.?|m\.?s\.?|degree in [a-z ]+)",
    re.I,
)
_WORK_AUTH = re.compile(
    r"(authoriz\w* to work|work authorization|eligible to work|"
    r"without (?:visa )?sponsorship|no (?:visa )?sponsorship|"
    r"security clearance|must be located)",
    re.I,
)
_SENIORITY = re.compile(r"\b(intern|junior|mid|senior|staff|principal|lead|director)\b", re.I)


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - pad): end + pad]).strip()


class Extractor(Protocol):
    def extract(self, posting: Posting) -> Requirements: ...


class HeuristicExtractor:
    """Deterministic, offline extractor. Precision-first; no fabrication."""

    def __init__(self) -> None:
        self._tokens = recognizable_tokens()  # raw token -> canonical
        # word-boundary patterns, longest tokens first so multiword wins
        self._patterns = [
            (re.compile(r"\b" + re.escape(tok) + r"\b", re.I), canon)
            for tok, canon in sorted(self._tokens.items(), key=lambda kv: -len(kv[0]))
        ]

    def _marker_positions(self, low: str) -> list[tuple[int, str]]:
        marks: list[tuple[int, str]] = []
        for m in _MUST_MARKERS:
            for mt in re.finditer(re.escape(m), low):
                marks.append((mt.start(), "must"))
        for m in _NICE_MARKERS:
            for mt in re.finditer(re.escape(m), low):
                marks.append((mt.start(), "nice"))
        marks.sort()
        return marks

    @staticmethod
    def _bucket_for(pos: int, marks: list[tuple[int, str]]) -> str:
        kind = "must"  # default: unmarked skills treated as required
        for mpos, mkind in marks:
            if mpos <= pos:
                kind = mkind
            else:
                break
        return kind

    def extract(self, posting: Posting) -> Requirements:
        text = f"{posting.title}. {posting.description}"
        low = text.lower()
        marks = self._marker_positions(low)

        must: list[str] = []
        nice: list[str] = []
        evidence: dict[str, str] = {}
        for pat, canon in self._patterns:
            m = pat.search(text)
            if not m:
                continue
            if canon in evidence:  # already recorded via a longer synonym
                continue
            bucket = self._bucket_for(m.start(), marks)
            (nice if bucket == "nice" else must).append(canon)
            evidence[canon] = _snippet(text, m.start(), m.end())

        # de-overlap: a skill in both buckets stays must
        nice = [s for s in nice if s not in must]

        years = None
        yrs = [int(x) for x in _YEARS.findall(low)]
        if yrs:
            years = min(yrs)
            evidence["years_experience"] = _snippet(low, *_YEARS.search(low).span())

        remote_policy = posting.remote_policy or None
        rm = _REMOTE.search(low)
        if not remote_policy and rm:
            remote_policy = rm.group(1).replace("onsite", "on-site")

        education = None
        em = _EDU.search(text)
        if em:
            education = em.group(0)
            evidence["education"] = _snippet(text, *em.span())

        work_auth = None
        hard: list[str] = []
        wm = _WORK_AUTH.search(text)
        if wm:
            work_auth = wm.group(0)
            hard.append("work_authorization")
            evidence["work_authorization"] = _snippet(text, *wm.span())

        seniority = None
        sm = _SENIORITY.search(posting.title)
        if sm:
            seniority = sm.group(1).lower()

        return Requirements(
            must_have_skills=must,
            nice_to_have_skills=nice,
            years_experience=years,
            education=education,
            remote_policy=remote_policy,
            work_authorization=work_auth,
            seniority=seniority,
            location=posting.location or None,
            application_method=f"{posting.source}:{posting.source_url}",
            hard_requirements=hard,
            evidence=evidence,
        )


_LLM_SYSTEM = (
    "You read a job description and list only the CONCRETE technical skills it "
    "asks for: programming languages, frameworks, libraries, databases, cloud "
    "services, tools, and platforms — the kind of thing you'd put in a resume "
    "skills section (e.g. python, kubernetes, postgres, react, kafka, "
    "distributed systems). "
    "Do NOT include responsibilities, job duties, soft skills, seniority, or "
    "team/culture phrases (e.g. NOT 'backend engineering', 'globally distributed "
    "teams', 'improving build systems', 'ownership', 'collaboration'). "
    "Prefer 1-2 word names. Return ONLY a JSON object: "
    '{"must_have_skills": [...], "nice_to_have_skills": [...]}. '
    "must_have = required; nice_to_have = preferred/bonus. No commentary, no "
    "other keys, and do not invent skills that are not in the text."
)

# words that mark a phrase as a responsibility/soft-skill, not a listable tech
_NON_SKILL_WORDS = {
    "team", "teams", "culture", "stakeholder", "stakeholders", "mentoring",
    "collaboration", "ownership", "responsibilities", "communication",
    "leadership", "experience", "engineering", "duties", "mindset",
}


def _looks_like_skill(name: str) -> bool:
    """Cheap guard against the model returning responsibility/culture phrases."""
    words = name.split()
    if len(words) > 3:
        return False
    if any(w in _NON_SKILL_WORDS for w in words):
        return False
    # a multi-word phrase led by a gerund is a responsibility ("improving build
    # systems"), not a skill — unlike "machine learning" / "distributed systems"
    if len(words) > 1 and words[0].endswith("ing") and len(words[0]) > 4:
        return False
    return True


def _ground_skills(names, jd: str, jd_low: str) -> tuple[list[str], dict[str, str]]:
    """Keep only model-returned skills that (a) look like a concrete skill and
    (b) actually appear in the JD (word boundary); normalize + record a JD
    snippet as evidence. The JD-match is the anti-fabrication guard; the
    look-like-a-skill filter drops responsibility/culture phrases the model
    sometimes returns."""
    kept: list[str] = []
    ev: dict[str, str] = {}
    for name in names or []:
        n = str(name).strip().lower()
        if not n or not _looks_like_skill(n):
            continue
        m = re.search(r"\b" + re.escape(n) + r"\b", jd_low)
        if not m:
            continue
        canon = normalize_skill(n)
        if canon not in kept:
            kept.append(canon)
            ev[canon] = _snippet(jd, m.start(), m.end())
    return kept, ev


class BedrockExtractor:
    """LLM-augmented extractor: the model widens skill recall, the heuristic
    supplies the deterministic fields, and Python grounds every skill against
    the JD.

    The model returns ONLY short skill-name arrays — trivial to emit as valid
    JSON (the earlier verbatim-quote design produced unparseable JSON). Skills
    are then grounded in `_ground_skills` (word-boundary match against the JD),
    so a fabricated skill can't survive. years / education / work-authorization /
    seniority / remote come from the deterministic HeuristicExtractor.
    """

    def __init__(self, llm: "object | None" = None) -> None:
        from src.llm.bedrock import BedrockLLM

        self.llm = llm or BedrockLLM()
        self._heur = HeuristicExtractor()

    def extract(self, posting: Posting) -> Requirements:
        reqs = self._heur.extract(posting)          # deterministic baseline
        jd = f"{posting.title}\n{posting.description}"
        data = self.llm.converse_json(_LLM_SYSTEM, jd, max_tokens=400, temperature=0.0)

        jd_low = jd.lower()
        must, ev_must = _ground_skills(data.get("must_have_skills", []), jd, jd_low)
        nice, ev_nice = _ground_skills(data.get("nice_to_have_skills", []), jd, jd_low)

        # union LLM skills with the heuristic baseline; must wins over nice
        merged_must = _dedupe(reqs.must_have_skills + must)
        merged_nice = [s for s in _dedupe(reqs.nice_to_have_skills + nice)
                       if s not in merged_must]
        reqs.must_have_skills = merged_must
        reqs.nice_to_have_skills = merged_nice
        reqs.evidence = {**reqs.evidence, **ev_must, **ev_nice}
        return reqs


def _dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    for x in items:
        if x not in out:
            out.append(x)
    return out


_DEFAULT = HeuristicExtractor()


def extract_requirements(posting: Posting, extractor: Optional[Extractor] = None) -> Requirements:
    return (extractor or _DEFAULT).extract(posting)
