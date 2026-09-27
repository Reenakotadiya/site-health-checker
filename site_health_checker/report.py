"""Turn a crawl result into findings, an HTML report, JSON and a console summary."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from html import escape

from site_health_checker import __version__
from site_health_checker.accessibility import RULES, SEVERITY_ORDER, Issue, page_score
from site_health_checker.crawler import CrawlResult, LinkResult, PageResult

A11Y_ROW_LIMIT = 50  # per rule in the HTML report; JSON always has everything


@dataclass
class Findings:
    broken_links: list[LinkResult]
    slow_pages: list[PageResult]
    redirect_chains: list[LinkResult]
    missing_titles: list[PageResult]
    a11y_issues: list[tuple[PageResult, Issue]]
    a11y_score: int | None  # None when no HTML pages could be checked

    @property
    def total_issues(self) -> int:
        return (len(self.broken_links) + len(self.slow_pages) + len(self.redirect_chains)
                + len(self.missing_titles) + len(self.a11y_issues))

    def a11y_by_rule(self) -> dict[str, list[tuple[PageResult, Issue]]]:
        """Issues grouped by rule, most severe rules first."""
        groups: dict[str, list[tuple[PageResult, Issue]]] = {}
        for page, issue in self.a11y_issues:
            groups.setdefault(issue.rule, []).append((page, issue))
        return dict(sorted(groups.items(), key=lambda kv: (SEVERITY_ORDER.index(RULES[kv[0]].severity), -len(kv[1]))))


def analyze(result: CrawlResult, slow_threshold: float = 2.0) -> Findings:
    ok_html_pages = [p for p in result.pages if p.is_html and p.status and p.status < 400]
    scores = [page_score(p.a11y_issues) for p in ok_html_pages]
    return Findings(
        broken_links=sorted((link for link in result.links if link.broken), key=lambda link: link.url),
        slow_pages=sorted((p for p in ok_html_pages if p.load_time > slow_threshold), key=lambda p: -p.load_time),
        redirect_chains=[link for link in result.links if len(link.redirects) >= 2],
        missing_titles=[p for p in ok_html_pages if not p.title],
        a11y_issues=[(p, issue) for p in ok_html_pages for issue in p.a11y_issues],
        a11y_score=round(sum(scores) / len(scores)) if scores else None,
    )


def _status(link: LinkResult) -> str:
    return str(link.status) if link.status is not None else f"Error: {link.error or 'no response'}"


def _score_text(score: int | None) -> str:
    return f"{score}/100" if score is not None else "n/a"


def to_json(result: CrawlResult, findings: Findings) -> str:
    return json.dumps({
        "start_url": result.start_url,
        "pages_crawled": len(result.pages),
        "links_checked": len(result.links),
        "duration_seconds": round(result.duration, 2),
        "total_issues": findings.total_issues,
        "broken_links": [{"url": l.url, "status": l.status, "error": l.error, "found_on": sorted(l.found_on)}
                         for l in findings.broken_links],
        "accessibility": {
            "score": findings.a11y_score,
            "issues": [{"rule": i.rule, "title": RULES[i.rule].title, "severity": RULES[i.rule].severity,
                        "wcag": RULES[i.rule].wcag, "page": p.url, "element": i.element}
                       for p, i in findings.a11y_issues],
        },
        "slow_pages": [{"url": p.url, "load_time_seconds": round(p.load_time, 2)} for p in findings.slow_pages],
        "redirect_chains": [{"url": l.url, "hops": len(l.redirects), "chain": l.redirects + [l.final_url]}
                            for l in findings.redirect_chains],
        "missing_titles": [p.url for p in findings.missing_titles],
    }, indent=2)


def console_summary(result: CrawlResult, findings: Findings) -> str:
    pages, links = len(result.pages), len(result.links)
    affected = len({p.url for p, _ in findings.a11y_issues})
    lines = [
        f"\nSite Health Report for {result.start_url}",
        f"Crawled {pages} page{'s' * (pages != 1)} and checked {links} link{'s' * (links != 1)} in {result.duration:.1f}s\n",
        f"  {'✗' if findings.a11y_issues else '✓'} Accessibility score: {_score_text(findings.a11y_score)}"
        f" ({len(findings.a11y_issues)} issues on {affected} page{'s' * (affected != 1)})",
    ]
    for rule, items in findings.a11y_by_rule().items():
        lines.append(f"      {len(items):>4}  {RULES[rule].title} [{RULES[rule].severity}]")
    rows = [
        ("Broken links", len(findings.broken_links)),
        ("Slow pages", len(findings.slow_pages)),
        ("Redirect chains", len(findings.redirect_chains)),
        ("Pages missing a title", len(findings.missing_titles)),
    ]
    for label, count in rows:
        lines.append(f"  {'✗' if count else '✓'} {label}: {count}")
        if label == "Broken links":
            lines += [f"      {_status(link):>8}  {link.url}" for link in findings.broken_links[:10]]
            if count > 10:
                lines.append(f"      ... and {count - 10} more (see the report)")
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


def _a11y_section(findings: Findings) -> str:
    if not findings.a11y_issues:
        return '<p class="ok">✓ No issues found by the automated checks</p>'
    blocks = []
    for rule_id, items in findings.a11y_by_rule().items():
        rule = RULES[rule_id]
        rows = [[_link(page.url), f"<code>{escape(issue.element)}</code>" if issue.element else "—"]
                for page, issue in items[:A11Y_ROW_LIMIT]]
        more = (f'<p class="hint">+{len(items) - A11Y_ROW_LIMIT} more (see the JSON output for all)</p>'
                if len(items) > A11Y_ROW_LIMIT else "")
        blocks.append(f"""<div class="rule">
<h3>{escape(rule.title)} <span class="sev sev-{rule.severity}">{rule.severity.title()}</span> <span class="count">{len(items)} found</span></h3>
<p class="wcag">WCAG {escape(rule.wcag)}</p>
<p><strong>Why it matters:</strong> {escape(rule.why)}</p>
<p><strong>How to fix:</strong> {escape(rule.fix)}</p>
{_table(["Page", "Element"], rows)}{more}
</div>""")
    return "".join(blocks)


def to_html(result: CrawlResult, findings: Findings, slow_threshold: float) -> str:
    score = findings.a11y_score
    sections = [
        ("Broken links", "Links that return an error (4xx/5xx) or don't respond.",
         _table(["Status", "Broken URL", "Found on"],
                [[f'<span class="bad">{escape(_status(l))}</span>', _link(l.url), _found_on(l)]
                 for l in findings.broken_links])),
        (f"Accessibility · {_score_text(score)}",
         "Automated checks for common WCAG problems. Color contrast, keyboard use and screen reader "
         "flow can't be checked from HTML alone and still need a manual review.",
         _a11y_section(findings)),
        ("Slow pages", f"Pages that took longer than {slow_threshold:g}s to load.",
         _table(["Load time", "Page"], [[f"{p.load_time:.2f}s", _link(p.url)] for p in findings.slow_pages])),
        ("Redirect chains", "Links that redirect two or more times before reaching the final page. Each hop adds delay.",
         _table(["Hops", "Link", "Chain"],
                [[str(len(l.redirects)), _link(l.url), " → ".join(escape(u) for u in l.redirects + [l.final_url])]
                 for l in findings.redirect_chains])),
        ("Missing page titles", "Pages without a <title> hurt SEO and accessibility (WCAG 2.4.2), and look broken in browser tabs.",
         _table(["Page"], [[_link(p.url)] for p in findings.missing_titles])),
    ]
    cards = [
        (_score_text(score), "Accessibility score", score is not None and score < 90),
        (len(findings.broken_links), "Broken links", bool(findings.broken_links)),
        (len(findings.slow_pages), "Slow pages", bool(findings.slow_pages)),
        (len(findings.redirect_chains), "Redirect chains", bool(findings.redirect_chains)),
        (len(findings.missing_titles), "Missing titles", bool(findings.missing_titles)),
    ]
    cards_html = "".join(
        f'<div class="card{" has-issues" if bad else ""}"><div class="num">{value}</div><div>{label}</div></div>'
        for value, label, bad in cards
    )
    body = "".join(f"<section><h2>{escape(t)}</h2><p class='hint'>{escape(d)}</p>{content}</section>"
                   for t, d, content in sections)
    generated = datetime.now().strftime("%d %b %Y, %H:%M")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Site Health Report: {escape(result.start_url)}</title>
<style>
:root {{ --bg:#f6f7f9; --panel:#fff; --text:#1d2330; --muted:#5f6b7a; --line:#e3e6eb; --good:#1f8a4c; --bad:#c62d2d; --warn:#b35c00; --code:#eef1f5; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --panel:#1c2027; --text:#e7eaee; --muted:#9aa4b1; --line:#2c323b; --good:#4cc47f; --bad:#ff6b6b; --warn:#f0a44b; --code:#262b33; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
main {{ max-width:1100px; margin:0 auto; padding:32px 16px; }}
h1 {{ margin:0 0 4px; font-size:26px; }} h2 {{ margin:0 0 4px; font-size:19px; }} h3 {{ margin:0 0 2px; font-size:16px; }}
.meta, .hint, .wcag {{ color:var(--muted); margin:0 0 16px; }} .wcag {{ margin-bottom:8px; font-size:13px; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin:24px 0; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; border-top:4px solid var(--good); }}
.card.has-issues {{ border-top-color:var(--bad); }} .num {{ font-size:30px; font-weight:700; }} .has-issues .num {{ color:var(--bad); }}
section {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:20px; margin-bottom:16px; overflow-x:auto; }}
.rule {{ border-top:1px solid var(--line); padding:16px 0 4px; }} .rule p {{ margin:0 0 8px; }}
.sev {{ font-size:12px; font-weight:700; padding:2px 8px; border-radius:99px; color:#fff; vertical-align:middle; }}
.sev-critical {{ background:var(--bad); }} .sev-serious {{ background:var(--warn); }} .sev-moderate {{ background:var(--muted); }}
.count {{ font-size:13px; font-weight:400; color:var(--muted); }}
code {{ background:var(--code); padding:1px 5px; border-radius:4px; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-top:8px; }} th, td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; overflow-wrap:anywhere; }}
th {{ color:var(--muted); font-weight:600; font-size:13px; white-space:nowrap; }}
a {{ color:inherit; }} .bad {{ color:var(--bad); font-weight:600; }} .ok {{ color:var(--good); margin:0; }}
footer {{ color:var(--muted); font-size:13px; text-align:center; margin-top:24px; }}
</style></head>
<body><main>
<h1>Site Health Report</h1>
<p class="meta">{_link(result.start_url)} · {len(result.pages)} pages crawled · {len(result.links)} links checked · {result.duration:.1f}s · {generated}</p>
<div class="cards">{cards_html}</div>
{body}
<footer>Generated by site-health-checker v{__version__}</footer>
</main></body></html>
"""
