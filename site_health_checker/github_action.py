"""Glue for the GitHub Action: job summary, step outputs and a pull request comment.

Run as: python -m site_health_checker.github_action site-health-results.json
Reads the standard GitHub Actions environment variables; everything is optional
so it also works on forks and self-hosted runners.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

MARKER = "<!-- site-health-checker -->"  # lets us find and update our own comment
SEVERITY_ICON = {"critical": "🔴", "serious": "🟠", "moderate": "🟡"}


def _icon(ok: bool) -> str:
    return "✅" if ok else "❌"


def build_markdown(data: dict | None, url: str = "", run_url: str = "") -> str:
    """Markdown report for the job summary and the PR comment. `data` is None when the site didn't load."""
    lines = [MARKER, f"### 🩺 Site Health Check: {data['start_url'] if data else url}", ""]
    if data is None:
        lines.append("❌ **The website could not be loaded**, so no checks were run. "
                     "Check that the URL is correct and the site is up.")
        if run_url:
            lines += ["", f"[View workflow run]({run_url})"]
        return "\n".join(lines) + "\n"

    a11y = data["accessibility"]
    score = a11y["score"]
    rows = [
        ("♿ Accessibility score", f"{score}/100" if score is not None else "n/a", not a11y["issues"]),
        ("🔗 Broken links", len(data["broken_links"]), not data["broken_links"]),
        ("🐢 Slow pages", len(data["slow_pages"]), not data["slow_pages"]),
        ("🔀 Redirect chains", len(data["redirect_chains"]), not data["redirect_chains"]),
        ("🏷️ Missing page titles", len(data["missing_titles"]), not data["missing_titles"]),
    ]
    lines += ["| Check | Result | |", "|---|---|---|"]
    lines += [f"| {label} | {value} | {_icon(ok)} |" for label, value, ok in rows]
    lines += ["", f"Crawled {data['pages_crawled']} pages and checked {data['links_checked']} links "
                  f"in {data['duration_seconds']}s."]

    if a11y["issues"]:
        counts = Counter((i["severity"], i["title"]) for i in a11y["issues"])
        order = {"critical": 0, "serious": 1, "moderate": 2}
        lines += ["", "<details><summary><b>Accessibility issues</b></summary>", ""]
        lines += [f"- {SEVERITY_ICON[sev]} **{title}**: {n}"
                  for (sev, title), n in sorted(counts.items(), key=lambda kv: (order[kv[0][0]], -kv[1]))]
        lines += ["", "</details>"]

    if data["broken_links"]:
        lines += ["", "<details><summary><b>Broken links</b></summary>", ""]
        for link in data["broken_links"][:20]:
            status = link["status"] if link["status"] is not None else link["error"] or "no response"
            lines.append(f"- `{status}` {link['url']}")
        if len(data["broken_links"]) > 20:
            lines.append(f"- … and {len(data['broken_links']) - 20} more")
        lines += ["", "</details>"]

    if run_url:
        lines += ["", f"📄 Full HTML report: download the **site-health-report** artifact from the [workflow run]({run_url})."]
    return "\n".join(lines) + "\n"


def _api(method: str, url: str, token: str, body: dict | None = None):
    request = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or "null")


def upsert_pr_comment(body: str, token: str, repo: str, pr_number: int, api_url: str = "https://api.github.com") -> str:
    """Update our previous comment on the PR if there is one, otherwise create it. Returns 'updated' or 'created'."""
    # ponytail: only looks at the first 100 comments; paginate if very busy PRs ever need it
    comments = _api("GET", f"{api_url}/repos/{repo}/issues/{pr_number}/comments?per_page=100", token)
    for comment in comments:
        if MARKER in (comment.get("body") or ""):
            _api("PATCH", f"{api_url}/repos/{repo}/issues/comments/{comment['id']}", token, {"body": body})
            return "updated"
    _api("POST", f"{api_url}/repos/{repo}/issues/{pr_number}/comments", token, {"body": body})
    return "created"


def _pr_number() -> int | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).exists():
        return None
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    return (event.get("pull_request") or {}).get("number")


def main(argv: list[str]) -> int:
    results_path = Path(argv[0]) if argv else Path("site-health-results.json")
    data = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else None
    env = os.environ
    run_url = ""
    if env.get("GITHUB_REPOSITORY") and env.get("GITHUB_RUN_ID"):
        run_url = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{env['GITHUB_REPOSITORY']}/actions/runs/{env['GITHUB_RUN_ID']}"
    markdown = build_markdown(data, env.get("SHC_URL", ""), run_url)

    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(markdown)
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            out.write(f"accessibility-score={data['accessibility']['score'] if data else ''}\n")
            out.write(f"broken-links={len(data['broken_links']) if data else ''}\n")

    pr = _pr_number()
    if env.get("SHC_COMMENT", "true") == "true" and pr and env.get("SHC_TOKEN") and env.get("GITHUB_REPOSITORY"):
        try:
            action = upsert_pr_comment(markdown, env["SHC_TOKEN"], env["GITHUB_REPOSITORY"], pr,
                                       env.get("GITHUB_API_URL", "https://api.github.com"))
            print(f"Pull request comment {action}.")
        except (urllib.error.URLError, OSError) as exc:
            # Pull requests from forks get a read-only token; the check itself should still pass or fail on its merits.
            print(f"::warning::Could not comment on the pull request ({exc}). "
                  "Give the workflow 'pull-requests: write' permission to enable comments.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
