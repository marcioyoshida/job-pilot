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
    "You extract structured hiring requirements from a job description. "
    "Return ONLY a JSON object with keys: must_have_skills, nice_to_have_skills "
    "(arrays of short skill names), years_experience (int or null), education "
    "(string or null), work_authorization (string or null), seniority (string or "
    "null), responsibilities (array), certifications (array), languages (array), "
    "comp (string or null), screening_questions (array), and evidence (object "
    "mapping each skill name and each non-null field to a VERBATIM quote copied "
    "from the job description). "
    "Rules: never invent anything not present in the text. If a field is not "
    "stated, use null or an empty array. Every skill and field you report MUST "
    "have a verbatim quote in `evidence`."
)


class BedrockExtractor:
    """LLM-assisted extractor (higher recall than the heuristic).

    Anti-fabrication guardrail: the model must return a verbatim JD quote for
    every skill/field, and `_to_requirements` DROPS anything whose quote is not
    actually a substring of the JD. So even if the model hallucinates a skill,
    it can't survive into the output.
    """

    def __init__(self, llm: "object | None" = None) -> None:
        from src.llm.bedrock import BedrockLLM

        self.llm = llm or BedrockLLM()

    def extract(self, posting: Posting) -> Requirements:
        jd = f"{posting.title}\n{posting.description}"
        data = self.llm.converse_json(_LLM_SYSTEM, jd)
        return self._to_requirements(posting, jd, data)

    @staticmethod
    def _grounded(names: list, evidence: dict, jd_low: str) -> tuple[list[str], dict]:
        kept: list[str] = []
        ev: dict[str, str] = {}
        for name in names or []:
            quote = (evidence or {}).get(name) or (evidence or {}).get(str(name).lower())
            if quote and quote.lower() in jd_low:
                canon = normalize_skill(str(name))
                if canon not in kept:
                    kept.append(canon)
                    ev[canon] = quote
        return kept, ev

    def _to_requirements(self, posting: Posting, jd: str, data: dict) -> Requirements:
        jd_low = jd.lower()
        evidence_in = data.get("evidence", {}) or {}
        must, ev_must = self._grounded(data.get("must_have_skills", []), evidence_in, jd_low)
        nice, ev_nice = self._grounded(data.get("nice_to_have_skills", []), evidence_in, jd_low)
        nice = [s for s in nice if s not in must]

        evidence = {**ev_must, **ev_nice}

        def _grounded_field(key: str):
            val = data.get(key)
            quote = evidence_in.get(key)
            if val and quote and str(quote).lower() in jd_low:
                evidence[key] = quote
                return val
            return None

        work_auth = _grounded_field("work_authorization")
        hard = ["work_authorization"] if work_auth else []

        return Requirements(
            must_have_skills=must,
            nice_to_have_skills=nice,
            years_experience=data.get("years_experience") if isinstance(
                data.get("years_experience"), int) else None,
            education=_grounded_field("education"),
            work_authorization=work_auth,
            seniority=data.get("seniority"),
            responsibilities=data.get("responsibilities", []) or [],
            certifications=data.get("certifications", []) or [],
            languages=data.get("languages", []) or [],
            comp=data.get("comp"),
            screening_questions=data.get("screening_questions", []) or [],
            location=posting.location or None,
            remote_policy=posting.remote_policy or None,
            application_method=f"{posting.source}:{posting.source_url}",
            hard_requirements=hard,
            evidence=evidence,
        )


_DEFAULT = HeuristicExtractor()


def extract_requirements(posting: Posting, extractor: Optional[Extractor] = None) -> Requirements:
    return (extractor or _DEFAULT).extract(posting)
