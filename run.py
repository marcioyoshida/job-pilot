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
STORE_PATH = Path("applications/records.json")


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

    import os

    profile = _load_profile(args.profile)
    candidate = CandidateProfile.from_yaml(args.candidate)
    cand_skills = candidate.normalized_skills()
    state = JsonState(STATE_PATH)
    sources = _sources(profile)
    if not sources:
        print("No sources wired yet — implement one in src/ingest/ (Phase P0/P1).")
        return 0

    # LLM path (Bedrock) is opt-in; falls back to the offline heuristic on error.
    use_llm = getattr(args, "llm", False) or os.environ.get("JOBPILOT_USE_LLM", "").lower() in (
        "1", "true", "yes")
    llm = None
    extractor = None
    if use_llm:
        try:
            from src.extract.requirements import BedrockExtractor
            from src.llm.bedrock import BedrockLLM

            llm = BedrockLLM()
            extractor = BedrockExtractor(llm)
            print(f"LLM path ON (model={llm.model_id}).\n")
        except Exception as exc:  # noqa: BLE001
            print(f"LLM unavailable ({exc}); falling back to heuristic.\n")
            use_llm, llm, extractor = False, None, None

    collected = []
    for s in sources:
        collected.extend(s.fetch(profile))
    fresh = new_postings(collected, state)

    rows = []
    for p in fresh:
        try:
            reqs = extractor.extract(p) if extractor else extract_requirements(p)
        except Exception as exc:  # noqa: BLE001 - one bad LLM call shouldn't sink the run
            print(f"  extract failed for {p.company} ({exc}); using heuristic.")
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
            from src.apply.records import ApplicationRecord, ApplicationStore
            from src.tailor.build import build_materials, write_materials

            materials = build_materials(candidate, p, reqs, fit, llm=llm)
            path = write_materials(materials, p, args.materials_dir)
            ApplicationStore(STORE_PATH).upsert(ApplicationRecord(
                key=p.dedupe_key(), company=p.company, title=p.title,
                source=p.source, source_url=p.source_url,
                application_method=reqs.application_method,
                materials_path=str(path), status="drafted",
            ))
            print(f"         draft materials -> {path}  (PENDING YOUR APPROVAL)")
            made += 1
    if args.tailor:
        print(f"\n{made} draft(s) written & registered. Next: "
              f"`python run.py review` then `approve` then `submit`.")
    return 0


def cmd_review(args) -> int:
    from src.apply.records import ApplicationStore

    records = ApplicationStore(args.store).all()
    if not records:
        print("No applications yet. Run `pipeline --tailor` first.")
        return 0
    print(f"{len(records)} application(s):\n")
    for r in records:
        flag = {"drafted": "· needs approval", "approved": "✓ approved (unsubmitted)",
                "submitted": "✔ submitted"}.get(r.status, r.status)
        print(f"  [{r.status:<9}] {r.company} — {r.title}   {flag}")
        print(f"       key={r.key}  {r.source_url}")
        if r.receipt:
            print(f"       receipt: {r.receipt.get('method')} -> {r.receipt.get('confirmation')}")
    print("\nApprove with: python run.py approve --key <key> | --all")
    return 0


def cmd_approve(args) -> int:
    from src.apply.records import ApplicationStore

    store = ApplicationStore(args.store)
    targets = store.all() if args.all else [r for r in store.all() if r.key == args.key]
    if not targets:
        print("No matching drafted application. Use `review` to list keys.")
        return 1
    n = 0
    for r in targets:
        if r.status == "drafted":
            store.approve(r.key)
            print(f"approved: {r.company} — {r.title}")
            n += 1
    print(f"\n{n} approved. Submit with: python run.py submit")
    return 0


def cmd_submit(args) -> int:
    from src.apply.records import ApplicationStore
    from src.submit.submitter import ApprovalRequired, submit_record

    store = ApplicationStore(args.store)
    approved = [r for r in store.all() if r.status == "approved"]
    if not approved:
        print("Nothing approved to submit. Run `approve` first (approval is required).")
        return 0
    print(f"Submitting {len(approved)} approved application(s)...\n")
    for r in approved:
        try:
            receipt = submit_record(r, store, package_dir=args.package_dir)
        except (ApprovalRequired, FileNotFoundError, RuntimeError) as exc:
            print(f"  SKIP {r.company} — {r.title}: {exc}")
            continue
        print(f"  {receipt.method}: {r.company} — {r.title}")
        print(f"       -> {receipt.confirmation}")
    print("\nOne-click packages/email drafts are prepared for YOU to finish. "
          "Nothing was auto-sent.")
    return 0


def cmd_monitor(args) -> int:
    """Update application statuses from the inbox (FR-6.2)."""
    from src.apply.records import ApplicationStore
    from src.monitor.tracker import monitor_messages

    store = ApplicationStore(args.store)
    if not store.all():
        print("No applications to monitor. Run the apply loop first.")
        return 0

    if args.inbox:
        from src.monitor.inbox import FileInbox
        messages = list(FileInbox(args.inbox).fetch())
    elif args.gmail:
        from src.monitor.inbox import GmailImapInbox
        messages = list(GmailImapInbox(limit=args.limit).fetch())
    else:
        print("Choose an inbox: --inbox <file.json> or --gmail "
              "(needs GMAIL_ADDRESS + GMAIL_APP_PASSWORD).")
        return 1

    def _notify(label: str, status: str) -> None:
        print(f"  🔔 {status.upper()}: {label}")

    transitions = monitor_messages(messages, store, notify=_notify)
    print(f"scanned {len(messages)} message(s); {len(transitions)} status change(s):")
    for _key, label, status in transitions:
        print(f"  {label} -> {status}")
    return 0


def cmd_status(args) -> int:
    """Manually override an application's status (FR-6.2 manual override)."""
    from src.apply.records import ApplicationStore
    from src.monitor.tracker import STATUSES

    if args.set not in STATUSES:
        print(f"unknown status '{args.set}'. One of: {', '.join(STATUSES)}")
        return 1
    store = ApplicationStore(args.store)
    if not store.get(args.key):
        print(f"no application with key {args.key} (see `review`).")
        return 1
    store.advance_status(args.key, args.set, source="manual",
                         detail="manual override", forward_only=False)
    print(f"{args.key} -> {args.set}")
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
            sp.add_argument("--llm", action="store_true",
                            help="use Bedrock for extraction + cover letter (needs AWS creds)")

    rv = sub.add_parser("review")
    rv.add_argument("--store", default=str(STORE_PATH))

    ap = sub.add_parser("approve")
    ap.add_argument("--store", default=str(STORE_PATH))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--key")
    g.add_argument("--all", action="store_true")

    sb = sub.add_parser("submit")
    sb.add_argument("--store", default=str(STORE_PATH))
    sb.add_argument("--package-dir", default="packages")

    mon = sub.add_parser("monitor")
    mon.add_argument("--store", default=str(STORE_PATH))
    mon.add_argument("--inbox", help="path to a JSON file of messages")
    mon.add_argument("--gmail", action="store_true",
                     help="read recent Gmail over IMAP (GMAIL_ADDRESS + GMAIL_APP_PASSWORD)")
    mon.add_argument("--limit", type=int, default=50)

    st = sub.add_parser("status")
    st.add_argument("--store", default=str(STORE_PATH))
    st.add_argument("--key", required=True)
    st.add_argument("--set", required=True, help="new lifecycle status")

    args = parser.parse_args(argv)
    handlers = {"gather": cmd_gather, "pipeline": cmd_pipeline,
                "review": cmd_review, "approve": cmd_approve, "submit": cmd_submit,
                "monitor": cmd_monitor, "status": cmd_status}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
