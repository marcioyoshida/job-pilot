import run
from src.ingest.base import Posting, SearchProfile


class _GoodSource:
    name = "good"

    def fetch(self, profile):
        return [Posting(source="good", source_url="u", company="Acme", title="Engineer")]


class _BadSource:
    name = "bad"

    def fetch(self, profile):
        raise RuntimeError("boom")


def test_collect_isolates_a_failing_source(capsys):
    got = run._collect([_BadSource(), _GoodSource()], SearchProfile())
    # the good source's posting survives even though the bad one raised
    assert [p.company for p in got] == ["Acme"]
    assert "source 'bad' failed: boom" in capsys.readouterr().out
