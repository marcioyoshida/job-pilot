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


def _require_config(path: str) -> Path:
    """Return the config path, or exit with a friendly copy-the-example hint."""
    p = Path(path)
    if p.exists():
        return p
    example = p.with_name(p.stem + ".example" + p.suffix)
    hint = f"cp {example} {p}   # then edit it" if example.exists() else f"create {p}"
    raise SystemExit(f"Config not found: {p}\n  → {hint}")


def _load_profile(path: str):
    import yaml  # local import so --help works without deps installed
    from src.ingest.base import SearchProfile

    data = yaml.safe_load(_require_config(path).read_text())
    return SearchProfile.from_dict(data or {})


def _linkedin_inbox(args):
    """Build the inbox that holds LinkedIn job-alert emails, or None."""
    if getattr(args, "linkedin_inbox", None):
        from src.monitor.inbox import FileInbox
        return FileInbox(args.linkedin_inbox)
    if getattr(args, "linkedin_gmail", False):
        from src.monitor.inbox import GmailImapInbox
        return GmailImapInbox(limit=getattr(args, "limit", 50))
    return None


def _collect(sources, profile):
    """Fetch from every source, isolating failures so one bad source (bad token,
    Gmail auth, network) never sinks the whole run."""
    collected = []
    for s in sources:
        try:
            collected.extend(s.fetch(profile))
        except Exception as exc:  # noqa: BLE001
            print(f"  source '{getattr(s, 'name', '?')}' failed: {exc}")
    return collected


def _sources(profile, linkedin_inbox=None):
    """Build the enabled JobSource list. Wire real sources as they land."""
    from src.ingest.greenhouse import GreenhouseSource
    from src.ingest.lever import LeverSource

    sources = []
    if profile.greenhouse_boards:
        sources.append(GreenhouseSource(boards=profile.greenhouse_boards))
    if profile.lever_companies:
        sources.append(LeverSource(companies=profile.lever_companies))
    if linkedin_inbox is not None:
        from src.ingest.linkedin import LinkedInAlertsSource
        sources.append(LinkedInAlertsSource(linkedin_inbox))
    return sources


def cmd_gather(args) -> int:
    from src.diff.engine import new_postings
    from src.state.store import JsonState

    profile = _load_profile(args.profile)
    state = JsonState(STATE_PATH)
    sources = _sources(profile, _linkedin_inbox(args))
    if not sources:
        print("No sources configured. Set greenhouse_boards/lever_companies in the "
              "profile, or pass --linkedin-inbox/--linkedin-gmail.")
        return 0

    fresh = new_postings(_collect(sources, profile), state, ignore_seen=getattr(args, "all", False))
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
    candidate = CandidateProfile.from_yaml(_require_config(args.candidate))
    cand_skills = candidate.normalized_skills()
    state = JsonState(STATE_PATH)
    sources = _sources(profile, _linkedin_inbox(args))
    if not sources:
        print("No sources configured. Set greenhouse_boards/lever_companies in the "
              "profile, or pass --linkedin-inbox/--linkedin-gmail.")
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

    fresh = new_postings(_collect(sources, profile), state, ignore_seen=getattr(args, "all", False))

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
    from datetime import datetime, timezone

    from src.dashboard.render import feed_item

    made = 0
    feed = []
    for p, reqs, fit in rows:
        gaps = ", ".join(fit.gaps[:6]) or "none"
        print(f"  {fit.fit_score:>5.0%}  [{fit.recommendation:<7}] {p.company} — {p.title}")
        print(f"         gaps: {gaps}")
        print(f"         {p.source_url}")
        materials_key = None
        # Draft tailored materials for worth-applying roles (DRAFT — not submitted).
        if args.tailor and fit.recommendation in ("apply", "stretch"):
            from src.apply.records import ApplicationRecord, ApplicationStore
            from src.tailor.build import build_materials, write_materials

            materials = build_materials(candidate, p, reqs, fit, llm=llm)
            path = write_materials(materials, p, args.materials_dir)
            materials_key = str(path)
            ApplicationStore(STORE_PATH).upsert(ApplicationRecord(
                key=p.dedupe_key(), company=p.company, title=p.title,
                source=p.source, source_url=p.source_url,
                application_method=reqs.application_method,
                materials_path=str(path), status="drafted",
            ))
            print(f"         draft materials -> {path}  (PENDING YOUR APPROVAL)")
            made += 1
        feed.append(feed_item(p, fit, materials_key))

    import json as _json
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "items": feed}
    Path(args.feed_out).write_text(_json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\nfeed -> {args.feed_out}   (render with `python run.py dashboard`)")
    if args.tailor:
        print(f"{made} draft(s) written & registered. Next: "
              f"`python run.py review` then `approve` then `submit`.")
    return 0


def cmd_dashboard(args) -> int:
    """Render a feed.json into a standalone HTML dashboard."""
    import json

    from src.dashboard.render import render_feed_html

    feed_path = Path(args.feed)
    if not feed_path.exists():
        raise SystemExit(f"{feed_path} not found — run `pipeline` first (it writes feed.json).")
    payload = json.loads(feed_path.read_text())
    Path(args.out).write_text(render_feed_html(payload), encoding="utf-8")
    print(f"wrote {args.out}  ({len(payload.get('items', []))} postings) — open it in a browser.")
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


def cmd_import_resume(args) -> int:
    """Convert a resume file into config/candidate.yaml."""
    import os

    from src.profile.candidate import CandidateProfile
    from src.profile.import_resume import (
        build_profile_dict,
        profile_from_text_heuristic,
        profile_from_text_llm,
        read_resume_text,
        to_yaml,
    )

    try:
        text = read_resume_text(args.file)
    except (FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(str(exc))
    if not text.strip():
        raise SystemExit(f"no text extracted from {args.file}")

    use_llm = args.llm or os.environ.get("JOBPILOT_USE_LLM", "").lower() in ("1", "true", "yes")
    raw = None
    if use_llm:
        try:
            from src.llm.bedrock import BedrockLLM
            raw = profile_from_text_llm(text, BedrockLLM())
            print(f"structured with Bedrock ({BedrockLLM().model_id}).")
        except Exception as exc:  # noqa: BLE001
            print(f"LLM import failed ({exc}); using heuristic.")
    if raw is None:
        raw = profile_from_text_heuristic(text)

    profile = build_profile_dict(raw)
    # sanity: it must parse back into a CandidateProfile
    parsed = CandidateProfile.from_dict(profile)

    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"{out} already exists — pass --force to overwrite, or --out <path>.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_yaml(profile), encoding="utf-8")

    print(f"\nwrote {out}")
    print(f"  name:     {profile['name'] or '(none found)'}")
    print(f"  headline: {profile['headline'] or '(none found)'}")
    print(f"  skills:   {len(parsed.normalized_skills())}  ({', '.join(parsed.normalized_skills()[:10])}…)")
    print(f"  bullets:  {len(profile['master_bullets'])}")
    print("\nReview it before running the pipeline — this profile drives fit + tailoring.")
    return 0


def cmd_export_config(args) -> int:
    """Convert local YAML config to JSON for the Lambda to read from S3."""
    import json

    import yaml

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name in ("search_profile", "candidate"):
        src = _require_config(f"config/{name}.yaml")
        data = yaml.safe_load(src.read_text()) or {}
        (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"wrote {out / (name + '.json')}")
    print(f"\nUpload to S3:\n  aws s3 cp {out}/search_profile.json s3://<bucket>/config/\n"
          f"  aws s3 cp {out}/candidate.json       s3://<bucket>/config/")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-pilot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("gather", "pipeline"):
        sp = sub.add_parser(name)
        sp.add_argument("--profile", default="config/search_profile.yaml")
        sp.add_argument("--linkedin-inbox",
                        help="JSON file of LinkedIn job-alert emails to ingest as a source")
        sp.add_argument("--linkedin-gmail", action="store_true",
                        help="read LinkedIn job-alert emails from Gmail (IMAP) as a source")
        sp.add_argument("--limit", type=int, default=50)
        sp.add_argument("--all", action="store_true",
                        help="reprocess every fetched posting, ignoring the seen-set "
                             "(does not update it)")
        if name == "pipeline":
            sp.add_argument("--candidate", default="config/candidate.yaml")
            sp.add_argument("--tailor", action="store_true",
                            help="write DRAFT tailored materials for apply/stretch roles")
            sp.add_argument("--materials-dir", default="materials")
            sp.add_argument("--feed-out", default="feed.json",
                            help="where to write the ranked feed (for the dashboard)")
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

    ir = sub.add_parser("import-resume")
    ir.add_argument("--file", required=True, help="resume file (.pdf/.docx/.txt/.md)")
    ir.add_argument("--out", default="config/candidate.yaml")
    ir.add_argument("--llm", action="store_true", help="structure with Bedrock (recommended)")
    ir.add_argument("--force", action="store_true", help="overwrite an existing --out")

    ec = sub.add_parser("export-config")
    ec.add_argument("--out-dir", default="build/cloud-config")

    db = sub.add_parser("dashboard")
    db.add_argument("--feed", default="feed.json")
    db.add_argument("--out", default="dashboard.html")

    args = parser.parse_args(argv)
    handlers = {"gather": cmd_gather, "pipeline": cmd_pipeline,
                "review": cmd_review, "approve": cmd_approve, "submit": cmd_submit,
                "monitor": cmd_monitor, "status": cmd_status,
                "import-resume": cmd_import_resume, "export-config": cmd_export_config,
                "dashboard": cmd_dashboard}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
