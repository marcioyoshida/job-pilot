from src.diff.engine import new_postings
from src.ingest.base import Posting
from src.state.store import JsonState


def _p(company, title, url, desc="jd", location="Remote"):
    return Posting(source="test", source_url=url, company=company,
                   title=title, location=location, description=desc)


def test_new_only_and_dedupe_within_batch(tmp_path):
    state = JsonState(tmp_path / "s.json")
    batch = [
        _p("Acme", "Engineer", "u1"),
        _p("Acme", "Engineer", "u2"),   # same role cross-listed -> dedupe key collides
        _p("Beta", "Analyst", "u3"),
    ]
    fresh = new_postings(batch, state)
    assert {p.company for p in fresh} == {"Acme", "Beta"}
    assert len(fresh) == 2


def test_marks_seen_across_runs(tmp_path):
    path = tmp_path / "s.json"
    first = new_postings([_p("Acme", "Engineer", "u1")], JsonState(path))
    assert len(first) == 1
    # new run, reloaded state -> already seen
    second = new_postings([_p("Acme", "Engineer", "u1")], JsonState(path))
    assert second == []


def test_no_mark_leaves_state_clean(tmp_path):
    path = tmp_path / "s.json"
    new_postings([_p("Acme", "Engineer", "u1")], JsonState(path), mark=False)
    again = new_postings([_p("Acme", "Engineer", "u1")], JsonState(path))
    assert len(again) == 1


def test_ignore_seen_reprocesses_without_touching_state(tmp_path):
    path = tmp_path / "s.json"
    # first run marks it seen
    new_postings([_p("Acme", "Engineer", "u1")], JsonState(path))
    # ignore_seen returns it again AND still dedupes within the batch
    got = new_postings([_p("Acme", "Engineer", "u1"), _p("Acme", "Engineer", "u2")],
                       JsonState(path), ignore_seen=True)
    assert len(got) == 1
    # state was not modified: a normal run still treats it as already seen
    assert new_postings([_p("Acme", "Engineer", "u1")], JsonState(path)) == []
