import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from site_health_checker import github_action
from site_health_checker.github_action import MARKER, build_markdown, upsert_pr_comment

RESULTS = {
    "start_url": "https://shop.test/",
    "pages_crawled": 6,
    "links_checked": 7,
    "duration_seconds": 2.3,
    "broken_links": [{"url": "https://shop.test/careers", "status": 404, "error": "", "found_on": ["https://shop.test/"]}],
    "accessibility": {"score": 69, "issues": [
        {"rule": "image-alt", "title": "Image has no alt text", "severity": "critical", "wcag": "1.1.1",
         "page": "https://shop.test/", "element": '<img src="a.png">'},
        {"rule": "image-alt", "title": "Image has no alt text", "severity": "critical", "wcag": "1.1.1",
         "page": "https://shop.test/p", "element": '<img src="b.png">'},
        {"rule": "page-has-h1", "title": "Page has no main heading (h1)", "severity": "moderate", "wcag": "",
         "page": "https://shop.test/p", "element": ""},
    ]},
    "slow_pages": [],
    "redirect_chains": [],
    "missing_titles": [],
}


def test_markdown_summarizes_results():
    md = build_markdown(RESULTS, run_url="https://github.com/o/r/actions/runs/1")
    assert md.startswith(MARKER)
    assert "| ♿ Accessibility score | 69/100 | ❌ |" in md
    assert "| 🔗 Broken links | 1 | ❌ |" in md
    assert "| 🐢 Slow pages | 0 | ✅ |" in md
    assert "🔴 **Image has no alt text**: 2" in md
    assert md.index("Image has no alt text") < md.index("Page has no main heading")  # most severe first
    assert "`404` https://shop.test/careers" in md
    assert "actions/runs/1" in md


def test_markdown_when_site_did_not_load():
    md = build_markdown(None, url="https://down.test")
    assert "could not be loaded" in md and "https://down.test" in md


class _FakeGitHub(BaseHTTPRequestHandler):
    comments: list = []
    status = 200

    def log_message(self, *args):
        pass

    def _reply(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        return json.loads(self.rfile.read(int(self.headers["Content-Length"])))

    def do_GET(self):
        if self.status != 200:
            return self._reply({"message": "Resource not accessible by integration"}, self.status)
        self._reply(self.comments)

    def do_POST(self):
        self.comments.append({"id": len(self.comments) + 1, "body": self._body()["body"]})
        self._reply(self.comments[-1], 201)

    def do_PATCH(self):
        comment_id = int(self.path.rsplit("/", 1)[1])
        comment = next(c for c in self.comments if c["id"] == comment_id)
        comment["body"] = self._body()["body"]
        self._reply(comment)


@pytest.fixture
def fake_github():
    _FakeGitHub.comments = [{"id": 1, "body": "Looks good to me!"}]  # someone else's comment
    _FakeGitHub.status = 200
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeGitHub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_pr_comment_is_created_then_updated_not_duplicated(fake_github):
    assert upsert_pr_comment(MARKER + " first", "t", "o/r", 7, fake_github) == "created"
    assert upsert_pr_comment(MARKER + " second", "t", "o/r", 7, fake_github) == "updated"
    ours = [c for c in _FakeGitHub.comments if MARKER in c["body"]]
    assert len(ours) == 1 and ours[0]["body"].endswith("second")
    assert _FakeGitHub.comments[0]["body"] == "Looks good to me!"  # never touches other comments


def _action_env(monkeypatch, tmp_path, api_url):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7}}))
    summary, output = tmp_path / "summary.md", tmp_path / "output.txt"
    for key, value in {
        "GITHUB_EVENT_PATH": str(event), "GITHUB_STEP_SUMMARY": str(summary), "GITHUB_OUTPUT": str(output),
        "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "1", "GITHUB_API_URL": api_url,
        "SHC_TOKEN": "t", "SHC_COMMENT": "true",
    }.items():
        monkeypatch.setenv(key, value)
    return summary, output


def test_main_writes_summary_outputs_and_comment(fake_github, monkeypatch, tmp_path):
    summary, output = _action_env(monkeypatch, tmp_path, fake_github)
    results = tmp_path / "results.json"
    results.write_text(json.dumps(RESULTS))

    assert github_action.main([str(results)]) == 0
    assert "69/100" in summary.read_text()
    assert "accessibility-score=69" in output.read_text() and "broken-links=1" in output.read_text()
    assert any(MARKER in c["body"] for c in _FakeGitHub.comments)


def test_main_warns_but_does_not_fail_without_comment_permission(fake_github, monkeypatch, tmp_path, capsys):
    _action_env(monkeypatch, tmp_path, fake_github)
    _FakeGitHub.status = 403  # e.g. a pull request from a fork
    assert github_action.main([str(tmp_path / "missing.json")]) == 0
    assert "::warning::Could not comment" in capsys.readouterr().out
