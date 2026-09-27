"""Turn a crawl result into findings, an HTML report, JSON and a console summary."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from html import escape

from site_health_checker import __version__
from site_health_checker.crawler import CrawlResult, LinkResult, PageResult


@dataclass
class Findings:
    broken_links: list[LinkResult]
    slow_pages: list[PageResult]
    missing_alt: list[PageResult]
    redirect_chains: list[LinkResult]
    missing_titles: list[PageResult]

    @property
    def total_issues(self) -> int:
        return (len(self.broken_links) + len(self.slow_pages) + len(self.missing_alt)
                + len(self.redirect_chains) + len(self.missing_titles))


def analyze(result: CrawlResult, slow_threshold: float = 2.0) -> Findings:
    ok_html_pages = [p for p in result.pages if p.is_html and p.status and p.status < 400]
    return Findings(
        broken_links=sorted((link for link in result.links if link.broken), key=lambda link: link.url),
        slow_pages=sorted((p for p in ok_html_pages if p.load_time > slow_threshold), key=lambda p: -p.load_time),
        missing_alt=[p for p in ok_html_pages if p.images_missing_alt],
        redirect_chains=[link for link in result.links if len(link.redirects) >= 2],
        missing_titles=[p for p in ok_html_pages if not p.title],
    )


def _status(link: LinkResult) -> str:
    return str(link.status) if link.status is not None else f"Error: {link.error or 'no response'}"


def to_json(result: CrawlResult, findings: Findings) -> str:
    return json.dumps({
        "start_url": result.start_url,
        "pages_crawled": len(result.pages),
        "links_checked": len(result.links),
        "duration_seconds": round(result.duration, 2),
        "total_issues": findings.total_issues,
        "broken_links": [{"url": l.url, "status": l.status, "error": l.error, "found_on": sorted(l.found_on)}
                         for l in findings.broken_links],
        "slow_pages": [{"url": p.url, "load_time_seconds": round(p.load_time, 2)} for p in findings.slow_pages],
        "images_missing_alt": [{"page": p.url, "images": p.images_missing_alt} for p in findings.missing_alt],
        "redirect_chains": [{"url": l.url, "hops": len(l.redirects), "chain": l.redirects + [l.final_url]}
                            for l in findings.redirect_chains],
        "missing_titles": [p.url for p in findings.missing_titles],
    }, indent=2)


def console_summary(result: CrawlResult, findings: Findings) -> str:
    rows = [
        ("Broken links", len(findings.broken_links)),
        ("Slow pages", len(findings.slow_pages)),
        ("Pages with images missing alt", len(findings.missing_alt)),
        ("Redirect chains", len(findings.redirect_chains)),
        ("Pages missing a title", len(findings.missing_titles)),
    ]
    pages, links = len(result.pages), len(result.links)
    lines = [
        f"\nSite Health Report for {result.start_url}",
        f"Crawled {pages} page{'s' * (pages != 1)} and checked {links} link{'s' * (links != 1)} in {result.duration:.1f}s\n",
    ]
    lines += [f"  {'✗' if count else '✓'} {label}: {count}" for label, count in rows]
    for link in findings.broken_links[:10]:
        lines.append(f"      {_status(link):>8}  {link.url}")
    if len(findings.broken_links) > 10:
        lines.append(f"      ... and {len(findings.broken_links) - 10} more (see the report)")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="ok">✓ No issues found</p>'
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _link(url: str) -> str:
    return f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(url)}</a>'


def _found_on(link: LinkResult) -> str:
    pages = sorted(link.found_on)
    shown = "<br>".join(_link(p) for p in pages[:3])
    return shown + (f"<br><small>+{len(pages) - 3} more</small>" if len(pages) > 3 else "")


def to_html(result: CrawlResult, findings: Findings, slow_threshold: float) -> str:
    sections = [
        ("Broken links", "Links that return an error (4xx/5xx) or don't respond.",
         _table(["Status", "Broken URL", "Found on"],
                [[f'<span class="bad">{escape(_status(l))}</span>', _link(l.url), _found_on(l)]
                 for l in findings.broken_links])),
        ("Slow pages", f"Pages that took longer than {slow_threshold:g}s to load.",
         _table(["Load time", "Page"],
                [[f"{p.load_time:.2f}s", _link(p.url)] for p in findings.slow_pages])),
        ("Images missing alt text", "Images without an alt attribute are an accessibility problem for screen readers.",
         _table(["Page", "Images"],
                [[_link(p.url), "<br>".join(escape(src) for src in p.images_missing_alt)] for p in findings.missing_alt])),
        ("Redirect chains", "Links that redirect two or more times before reaching the final page. Each hop adds delay.",
         _table(["Hops", "Link", "Chain"],
                [[str(len(l.redirects)), _link(l.url), " → ".join(escape(u) for u in l.redirects + [l.final_url])]
                 for l in findings.redirect_chains])),
        ("Missing page titles", "Pages without a <title> hurt SEO and look broken in browser tabs.",
         _table(["Page"], [[_link(p.url)] for p in findings.missing_titles])),
    ]
    cards = "".join(
        f'<div class="card{" has-issues" if count else ""}"><div class="num">{count}</div><div>{label}</div></div>'
        for label, count in [(title, len(items)) for title, items in [
            ("Broken links", findings.broken_links), ("Slow pages", findings.slow_pages),
            ("Images missing alt", findings.missing_alt), ("Redirect chains", findings.redirect_chains),
            ("Missing titles", findings.missing_titles)]]
    )
    body = "".join(f"<section><h2>{t}</h2><p class='hint'>{escape(d)}</p>{table}</section>" for t, d, table in sections)
    generated = datetime.now().strftime("%d %b %Y, %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site Health Report: {escape(result.start_url)}</title>
<style>
:root {{ --bg:#f6f7f9; --panel:#fff; --text:#1d2330; --muted:#5f6b7a; --line:#e3e6eb; --good:#1f8a4c; --bad:#c62d2d; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --panel:#1c2027; --text:#e7eaee; --muted:#9aa4b1; --line:#2c323b; --good:#4cc47f; --bad:#ff6b6b; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1100px; margin:0 auto; padding:32px 16px; }}
h1 {{ margin:0 0 4px; font-size:26px; }} h2 {{ margin:0 0 4px; font-size:19px; }}
.meta, .hint {{ color:var(--muted); margin:0 0 16px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:24px 0; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; border-top:4px solid var(--good); }}
.card.has-issues {{ border-top-color:var(--bad); }} .num {{ font-size:30px; font-weight:700; }} .has-issues .num {{ color:var(--bad); }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:20px; margin-bottom:16px; overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; }} th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; word-break:break-all; }}
th {{ color:var(--muted); font-weight:600; font-size:13px; }}
a {{ color:inherit; }} .bad {{ color:var(--bad); font-weight:600; }} .ok {{ color:var(--good); margin:0; }}
footer {{ color:var(--muted); font-size:13px; text-align:center; margin-top:24px; }}
</style></head>
<body><main>
<h1>Site Health Report</h1>
<p class="meta">{_link(result.start_url)} · {len(result.pages)} pages crawled · {len(result.links)} links checked · {result.duration:.1f}s · {generated}</p>
<div class="cards">{cards}</div>
{body}
<footer>Generated by site-health-checker v{__version__}</footer>
</main></body></html>
"""
