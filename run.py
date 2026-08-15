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

    sources = []
    if profile.greenhouse_boards:
        sources.append(GreenhouseSource(boards=profile.greenhouse_boards))
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
    print("pipeline: gather -> extract -> match -> tailor -> [approval] -> submit -> monitor")
    print("Only `gather` is wired end-to-end so far (see docs/2026-08-15-phase-plan.md).")
    return cmd_gather(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-pilot")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("gather", "pipeline"):
        sp = sub.add_parser(name)
        sp.add_argument("--profile", default="config/search_profile.yaml")
    args = parser.parse_args(argv)
    return {"gather": cmd_gather, "pipeline": cmd_pipeline}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
