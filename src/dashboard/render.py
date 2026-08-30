"""Render the ranked feed as a self-contained HTML dashboard.

`feed_item` builds the per-posting dict (shared by the local pipeline and the
Lambda so both emit the same feed shape). `render_feed_html` turns a feed payload
into one standalone page — no external assets, light/dark aware, accessible —
that a person opens locally or that is served from S3/CloudFront later.
"""
from __future__ import annotations

import html
from typing import Any

_REC_COLOR = {"apply": "#1a7f4b", "stretch": "#9a6a00", "skip": "#6b7280"}


def feed_item(posting, fit, materials_key: str | None = None) -> dict[str, Any]:
    item = {
        "key": posting.dedupe_key(),
        "company": posting.company,
        "title": posting.title,
        "source": posting.source,
        "source_url": posting.source_url,
        "fit_score": fit.fit_score,
        "recommendation": fit.recommendation,
        "estimated": fit.estimated,
        "gaps": fit.gaps,
    }
    if materials_key:
        item["materials_key"] = materials_key
    return item


def _esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def _card(item: dict[str, Any]) -> str:
    rec = str(item.get("recommendation", "review"))
    color = _REC_COLOR.get(rec, "#6b7280")
    pct = f"{float(item.get('fit_score', 0)) * 100:.0f}%"
    gaps = item.get("gaps") or []
    chips = "".join(f'<span class="chip">{_esc(g)}</span>' for g in gaps[:10]) or \
        '<span class="chip none">no gaps</span>'
    draft = ('<span class="draft">draft ready</span>' if item.get("materials_key") else "")
    url = _esc(item.get("source_url", ""))
    return f"""
    <article class="card">
      <div class="score" style="--c:{color}"><span>{pct}</span><small>{_esc(rec)}</small></div>
      <div class="body">
        <h2>{_esc(item.get('title', ''))}</h2>
        <div class="meta">{_esc(item.get('company', ''))} · {_esc(item.get('source', ''))} {draft}</div>
        <div class="gaps"><span class="lbl">gaps</span>{chips}</div>
        <a class="src" href="{url}" target="_blank" rel="noopener">view posting →</a>
      </div>
    </article>"""


def render_feed_html(payload: dict[str, Any]) -> str:
    items = payload.get("items", []) or []
    generated = _esc(payload.get("generated_at") or payload.get("run_id") or "")
    n_apply = sum(1 for i in items if i.get("recommendation") == "apply")
    n_draft = sum(1 for i in items if i.get("materials_key"))
    cards = "\n".join(_card(i) for i in items) or '<p class="empty">No postings in this feed.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>job-pilot feed</title>
<style>
  :root {{ --bg:#f6f7f9; --fg:#111827; --muted:#6b7280; --card:#ffffff; --line:#e5e7eb; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#0d1117; --fg:#e6edf3; --muted:#9198a1; --card:#161b22; --line:#30363d; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
  header {{ padding:24px 20px; border-bottom:1px solid var(--line); }}
  h1 {{ margin:0; font-size:20px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-top:4px; }}
  main {{ max-width:860px; margin:0 auto; padding:20px; display:flex; flex-direction:column; gap:12px; }}
  .card {{ display:flex; gap:16px; background:var(--card); border:1px solid var(--line);
    border-radius:12px; padding:16px; }}
  .score {{ flex:0 0 84px; text-align:center; border-right:1px solid var(--line); padding-right:12px;
    display:flex; flex-direction:column; justify-content:center; }}
  .score span {{ font-size:24px; font-weight:700; color:var(--c); }}
  .score small {{ text-transform:uppercase; letter-spacing:.05em; font-size:11px; color:var(--c); }}
  .body {{ flex:1; min-width:0; }}
  h2 {{ margin:0 0 2px; font-size:16px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:8px; }}
  .draft {{ background:#1a7f4b; color:#fff; font-size:11px; padding:1px 6px; border-radius:6px; margin-left:6px; }}
  .gaps {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px; }}
  .lbl {{ color:var(--muted); font-size:12px; margin-right:2px; }}
  .chip {{ background:var(--bg); border:1px solid var(--line); border-radius:999px;
    padding:1px 8px; font-size:12px; }}
  .chip.none {{ color:var(--muted); }}
  .src {{ color:#2563eb; text-decoration:none; font-size:13px; }}
  .src:hover {{ text-decoration:underline; }}
  .empty {{ color:var(--muted); text-align:center; padding:40px; }}
  .note {{ color:var(--muted); font-size:12px; }}
</style>
</head>
<body>
  <header>
    <h1>job-pilot feed</h1>
    <div class="sub">{len(items)} postings · {n_apply} apply · {n_draft} draft(s) ready · {generated}</div>
    <div class="note">Fit scores are estimated. Nothing is submitted without your approval.</div>
  </header>
  <main>
    {cards}
  </main>
</body>
</html>"""
