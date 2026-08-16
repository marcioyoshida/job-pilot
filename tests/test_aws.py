import json

from src.aws.handler import run_pipeline
from src.ingest.base import Posting, SearchProfile
from src.profile.candidate import CandidateProfile, MasterBullet
from src.state.store import DynamoDbState


class FakeTable:
    """Minimal in-memory stand-in for a boto3 DynamoDB Table."""

    def __init__(self):
        self.items = {}

    def get_item(self, Key):
        pk = Key["pk"]
        return {"Item": self.items[pk]} if pk in self.items else {}

    def put_item(self, Item):
        self.items[Item["pk"]] = Item


def test_dynamodb_state_seen_and_kv_roundtrip():
    st = DynamoDbState(table=FakeTable())
    assert st.seen("k1") is False
    st.mark_seen("k1")
    assert st.seen("k1") is True
    assert st.get("cursor") is None
    st.put("cursor", "2026-08-16")
    assert st.get("cursor") == "2026-08-16"


class _Source:
    name = "fake"

    def __init__(self, postings):
        self._postings = postings

    def fetch(self, profile):
        return self._postings


def _candidate():
    return CandidateProfile(
        name="Marcio", skills=["python", "aws"],
        master_bullets=[MasterBullet("b1", "Built AWS Lambda pipelines in Python.",
                                     ["python", "aws", "lambda"])],
    )


def test_run_pipeline_writes_feed_and_drafts_and_diffs():
    posts = [
        Posting(source="fake", source_url="u1", company="Acme", title="Python Engineer",
                description="Requirements: Python and AWS."),
        Posting(source="fake", source_url="u2", company="Globex", title="Rust Engineer",
                description="Requirements: Rust and C++."),
    ]
    written = {}
    state = DynamoDbState(table=FakeTable())
    from src.extract.requirements import HeuristicExtractor

    feed = run_pipeline([_Source(posts)], SearchProfile(recency_days=0), _candidate(),
                        state, HeuristicExtractor(),
                        lambda k, b: written.__setitem__(k, b), run_id="RUN1")

    # feed written (per-run + latest), sorted best-fit first
    assert "feed/RUN1.json" in written and "feed/latest.json" in written
    items = json.loads(written["feed/RUN1.json"])["items"]
    assert items[0]["company"] == "Acme"                      # python/aws match ranks first
    assert items[0]["fit_score"] >= items[1]["fit_score"]
    # a draft was written for the apply/stretch role, under the run prefix
    assert any(k.startswith("materials/RUN1/") for k in written)

    # second run over the same postings: diff engine -> nothing new
    written.clear()
    feed2 = run_pipeline([_Source(posts)], SearchProfile(recency_days=0), _candidate(),
                         state, HeuristicExtractor(),
                         lambda k, b: written.__setitem__(k, b), run_id="RUN2")
    assert feed2 == []
    assert json.loads(written["feed/RUN2.json"])["items"] == []


def test_run_pipeline_does_not_submit_anything():
    # drafts are marked pending approval; nothing here submits
    posts = [Posting(source="fake", source_url="u1", company="Acme", title="Python Engineer",
                     description="Requirements: Python and AWS.")]
    written = {}
    from src.extract.requirements import HeuristicExtractor

    run_pipeline([_Source(posts)], SearchProfile(recency_days=0), _candidate(),
                 DynamoDbState(table=FakeTable()), HeuristicExtractor(),
                 lambda k, b: written.__setitem__(k, b), run_id="RUN1")
    draft = next(json.loads(b) for k, b in written.items() if k.startswith("materials/"))
    assert draft["status"] == "draft_pending_approval"
