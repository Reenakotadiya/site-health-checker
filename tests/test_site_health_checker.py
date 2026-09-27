"""Tests run against a tiny local website, so they are fast and need no internet."""
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from site_health_checker import cli
from site_health_checker.accessibility import Issue
from site_health_checker.cli import main
from site_health_checker.crawler import CrawlResult, PageResult, crawl, normalize
from site_health_checker.report import analyze

PAGES = {
    "/": """<html><head><title>Home</title></head><body>
        <a href="/about">About</a>
        <a href="/missing">Missing page</a>
        <a href="/old">Old link that redirects twice</a>
        <a href="/slow">Slow page</a>
        <a href="/about#team">Same page with a fragment</a>
        <a href="mailto:hi@example.com">Email</a>
        <a href="/private/secret">Blocked by robots.txt</a>
        <img src="logo.png">
        <img src="divider.png" alt="">
        <img src="team.png" alt="Our team">
        </body></html>""",
    "/about": "<html><head></head><body><a href='/'>Home</a></body></html>",
    "/slow": "<html><head><title>Slow</title></head><body>slow</body></html>",
    "/private/secret": "<html><head><title>Secret</title></head><body><a href='/hidden'>x</a></body></html>",
}
REDIRECTS = {"/old": "/older", "/older": "/about"}


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _respond(self, send_body):
        if self.path == "/robots.txt":
            body, content_type, status = b"User-agent: *\nDisallow: /private/\n", "text/plain", 200
        elif self.path in REDIRECTS:
            self.send_response(301)
            self.send_header("Location", REDIRECTS[self.path])
            self.end_headers()
            return
        elif self.path in PAGES:
            if self.path == "/slow":
                time.sleep(0.3)
            body, content_type, status = PAGES[self.path].encode(), "text/html; charset=utf-8", 200
        else:
            body, content_type, status = b"Not found", "text/plain", 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def do_GET(self):
        self._respond(send_body=True)

    def do_HEAD(self):
        self._respond(send_body=False)


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="module")
def findings(site):
    result = crawl(site + "/", timeout=5)
    return result, analyze(result, slow_threshold=0.2)


def test_finds_broken_link_and_where_it_is(findings, site):
    _, found = findings
    assert [link.url for link in found.broken_links] == [site + "/missing"]
    assert found.broken_links[0].status == 404
    assert found.broken_links[0].found_on == {site + "/"}


def test_detects_redirect_chain(findings, site):
    _, found = findings
    [chain] = found.redirect_chains
    assert chain.url == site + "/old"
    assert len(chain.redirects) == 2
    assert chain.final_url == site + "/about"


def test_accessibility_issues_and_score(findings, site):
    _, found = findings
    image_issues = [(page.url, issue.element) for page, issue in found.a11y_issues if issue.rule == "image-alt"]
    assert image_issues == [(site + "/", '<img src="logo.png">')]  # alt="" is valid for decorative images
    assert 0 <= found.a11y_score < 100


def test_detects_missing_title_and_slow_page(findings, site):
    _, found = findings
    assert [p.url for p in found.missing_titles] == [site + "/about"]
    assert [p.url for p in found.slow_pages] == [site + "/slow"]


def test_respects_robots_txt_and_ignores_fragments(findings, site):
    result, _ = findings
    crawled = {page.url for page in result.pages}
    assert site + "/private/secret" not in crawled
    assert site + "/about#team" not in {link.url for link in result.links}


def test_respects_max_pages(site):
    assert len(crawl(site + "/", max_pages=1, timeout=5).pages) == 1


@pytest.mark.parametrize("href, expected", [
    ("/page#section", "https://example.com/page"),
    ("other", "https://example.com/dir/other"),
    ("mailto:a@b.com", None),
    ("javascript:void(0)", None),
    ("#top", None),
    ("ftp://example.com/file", None),
])
def test_normalize(href, expected):
    assert normalize("https://example.com/dir/index.html", href) == expected


def test_cli_writes_reports_and_fails_on_broken_links(site, tmp_path):
    html, report_json = tmp_path / "report.html", tmp_path / "report.json"
    exit_code = main([site, "-o", str(html), "--json", str(report_json), "--timeout", "5"])

    assert exit_code == 1
    assert "Site Health Report" in html.read_text()
    data = json.loads(report_json.read_text())
    assert data["broken_links"][0]["status"] == 404

    assert main([site, "-o", str(html), "--no-fail", "--timeout", "5"]) == 0


def test_cli_min_score_fails_the_build(monkeypatch, tmp_path):
    # A site with no broken links, whose only page scores 90 (one critical issue).
    page = PageResult("https://ok.test/", 200, 0.1, is_html=True, title="Home", a11y_issues=[Issue("image-alt")])
    monkeypatch.setattr(cli, "crawl", lambda *args, **kwargs: CrawlResult("https://ok.test/", [page], [], 0.1))
    html = str(tmp_path / "report.html")

    assert main(["https://ok.test", "-o", html]) == 0
    assert main(["https://ok.test", "-o", html, "--min-score", "90"]) == 0
    assert main(["https://ok.test", "-o", html, "--min-score", "95"]) == 1
