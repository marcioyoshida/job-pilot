"""job-pilot local orchestrator (Phase P).

Runs the pipeline stages locally with JsonState before the serverless port
(Phase P6). Only `gather` is wired end-to-end once a source is implemented; the
other stages print their planned step so the CLI shape is stable.

    python run.py gather   --profile config/search_profile.yaml
    python run.py pipeline --profile config/search_profile.yaml   # gather..tailor

Nothing is submitted without an explicit approval step (NFR-1).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

STATE_PATH = Path(".jobpilot/state.json")


def _load_profile(path: str):
    import yaml  # local import so --help works without deps installed
    from src.ingest.base import SearchProfile

    data = yaml.safe_load(Path(path).read_text())
    return SearchProfile.from_dict(data or {})


def _sources(profile):
    """Build the enabled JobSource list. Wire real sources as they land."""
    from src.ingest.greenhouse import GreenhouseSource
    from src.ingest.lever import LeverSource

    sources = []
    if profile.greenhouse_boards:
        sources.append(GreenhouseSource(boards=profile.greenhouse_boards))
    if profile.lever_companies:
        sources.append(LeverSource(companies=profile.lever_companies))
    # Phase P1: for acct in profile.linkedin_accounts:
    #               sources.append(LinkedInSource(acct["label"]))
    return sources


def cmd_gather(args) -> int:
    from src.diff.engine import new_postings
    from src.state.store import JsonState

    profile = _load_profile(args.profile)
    state = JsonState(STATE_PATH)
    sources = _sources(profile)
    if not sources:
        print("No sources wired yet — implement one in src/ingest/ (Phase P0/P1).")
        return 0

    collected = []
    for s in sources:
        collected.extend(s.fetch(profile))
    fresh = new_postings(collected, state)
    print(f"{len(fresh)} new posting(s) since last run:")
    for p in fresh:
        print(f"  [{p.source}] {p.company} — {p.title}  {p.source_url}")
    return 0


def cmd_pipeline(args) -> int:
    """gather -> extract -> match, ranked by fit for a candidate profile."""
    from src.diff.engine import new_postings
    from src.extract.requirements import extract_requirements
    from src.match.fit import analyze_fit
    from src.profile.candidate import CandidateProfile
    from src.state.store import JsonState

    profile = _load_profile(args.profile)
    candidate = CandidateProfile.from_yaml(args.candidate)
    cand_skills = candidate.normalized_skills()
    state = JsonState(STATE_PATH)
    sources = _sources(profile)
    if not sources:
        print("No sources wired yet — implement one in src/ingest/ (Phase P0/P1).")
        return 0

    collected = []
    for s in sources:
        collected.extend(s.fetch(profile))
    fresh = new_postings(collected, state)

    rows = []
    for p in fresh:
        reqs = extract_requirements(p)
        fit = analyze_fit(reqs, cand_skills)
        rows.append((p, reqs, fit))
    rows.sort(key=lambda r: r[2].fit_score, reverse=True)

    print(f"{len(rows)} new posting(s), ranked by fit (score is ESTIMATED):\n")
    made = 0
    for p, reqs, fit in rows:
        gaps = ", ".join(fit.gaps[:6]) or "none"
        print(f"  {fit.fit_score:>5.0%}  [{fit.recommendation:<7}] {p.company} — {p.title}")
        print(f"         gaps: {gaps}")
        print(f"         {p.source_url}")
        # Draft tailored materials for worth-applying roles (DRAFT — not submitted).
        if args.tailor and fit.recommendation in ("apply", "stretch"):
            from src.tailor.build import build_materials, write_materials

            materials = build_materials(candidate, p, reqs, fit)
            path = write_materials(materials, p, args.materials_dir)
            print(f"         draft materials -> {path}  (PENDING YOUR APPROVAL)")
            made += 1
    if args.tailor:
        print(f"\n{made} draft package(s) written. Review before any submission (Stage 5).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-pilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("gather", "pipeline"):
        sp = sub.add_parser(name)
        sp.add_argument("--profile", default="config/search_profile.yaml")
        if name == "pipeline":
            sp.add_argument("--candidate", default="config/candidate.yaml")
            sp.add_argument("--tailor", action="store_true",
                            help="write DRAFT tailored materials for apply/stretch roles")
            sp.add_argument("--materials-dir", default="materials")
    args = parser.parse_args(argv)
    return {"gather": cmd_gather, "pipeline": cmd_pipeline}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
