from src.dashboard.render import feed_item, render_feed_html
from src.ingest.base import FitAnalysis, Posting


def _posting(company="Acme", title="Senior Backend Engineer"):
    return Posting(source="greenhouse", source_url="https://x/jobs/1",
                   company=company, title=title)


def _fit(score=0.8, rec="apply", gaps=None):
    return FitAnalysis(fit_score=score, matched_skills=["python"], gaps=gaps or [],
                       recommendation=rec)


def test_feed_item_shape():
    it = feed_item(_posting(), _fit(), materials_key="materials/RUN/k.json")
    assert it["company"] == "Acme"
    assert it["fit_score"] == 0.8
    assert it["recommendation"] == "apply"
    assert it["materials_key"].endswith("k.json")


def test_render_contains_cards_and_counts():
    payload = {"generated_at": "2026-08-16T00:00:00Z", "items": [
        feed_item(_posting("Acme", "Python Eng"), _fit(0.9, "apply"),
                  materials_key="materials/RUN/a.json"),
        feed_item(_posting("Globex", "Rust Eng"), _fit(0.1, "skip", ["rust"])),
    ]}
    html = render_feed_html(payload)
    assert "<!doctype html>" in html.lower()
    assert "Python Eng" in html and "Globex" in html
    assert "90%" in html and "10%" in html
    assert "1 apply" in html and "1 draft(s) ready" in html
    assert "rust" in html                      # gap chip
    assert "draft ready" in html               # only the apply item


def test_render_escapes_html():
    payload = {"items": [feed_item(_posting("<script>", "A&B <b>title</b>"), _fit())]}
    html = render_feed_html(payload)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "A&amp;B" in html


def test_render_empty_feed():
    html = render_feed_html({"items": []})
    assert "No postings in this feed." in html
