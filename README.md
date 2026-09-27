# 🩺 Site Health Checker

[![Tests](https://github.com/Reenakotadiya/site-health-checker/actions/workflows/tests.yml/badge.svg)](https://github.com/Reenakotadiya/site-health-checker/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/site-health-checker)](https://pypi.org/project/site-health-checker/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io-2496ED?logo=docker&logoColor=white)](https://github.com/Reenakotadiya/site-health-checker/pkgs/container/site-health-checker)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Audit any website for accessibility and broken links in one command, with a report anyone can understand.**

Site Health Checker crawls your whole site and finds the problems that shut out users with disabilities, frustrate visitors and hurt SEO:

- ♿ **Accessibility (WCAG) problems**, explained in plain English with **how to fix each one**, plus an overall **score out of 100**
- ❌ **Broken links**: 404s, 500s and links that don't respond, plus the page each one appears on
- 🐢 **Slow pages**
- 🔀 **Redirect chains**: links that bounce through 2+ redirects
- 🏷️ **Missing page titles**

You get a clean **HTML report** you can hand to a developer, a manager or a client, plus **JSON** for CI pipelines.

![Sample report](docs/report-screenshot.png)

---

## 🚀 Quick Start

```bash
pip install site-health-checker

site-health-checker https://example.com
```

Then open `site-health-report.html` in your browser.

**No Python? Use Docker:**

```bash
docker run --rm -v "$PWD:/reports" ghcr.io/reenakotadiya/site-health-checker https://example.com
```

The report is saved in your current folder. Images are published for both `amd64` and `arm64` (including Apple Silicon Macs).

```
Site Health Report for https://example.com/
Crawled 6 pages and checked 7 links in 2.3s

  ✗ Accessibility score: 69/100 (17 issues on 3 pages)
         5  Image has no alt text [critical]
         3  Form field has no label [critical]
         1  Button has no text [critical]
         3  Zooming is disabled [serious]
         2  Link has no text [serious]
  ✗ Broken links: 2
           404  https://example.com/careers
  ✓ Slow pages: 0
  ✓ Redirect chains: 0
  ✓ Pages missing a title: 0
```

---

## ♿ Accessibility Checks

Why it matters: accessibility is a legal requirement in more and more places (such as the **European Accessibility Act** and the **ADA** in the US), and around 1 in 6 people worldwide lives with a disability.

| Check | Severity | WCAG |
|---|---|---|
| Image has no alt text | Critical | 1.1.1 |
| Form field has no label | Critical | 1.3.1 / 4.1.2 |
| Button has no text | Critical | 4.1.2 |
| Link has no text | Serious | 2.4.4 |
| Page language is not set | Serious | 3.1.1 |
| Zooming is disabled on mobile | Serious | 1.4.4 |
| Page title is missing | (reported separately) | 2.4.2 |
| Page has no main heading (h1) | Moderate | best practice |
| Heading levels are skipped | Moderate | best practice |

Every issue in the report comes with **why it matters** and **how to fix it**, written for people who aren't accessibility experts.

**The score:** each page starts at 100 and loses 10 points per critical issue, 5 per serious and 2 per moderate. The site score is the average across all pages.

> **Honest note:** automated checks catch many of the most common problems, but **no tool can prove a site is fully accessible.** Color contrast, keyboard navigation and how the page sounds in a screen reader still need a manual review. Use this tool to find and fix the obvious issues fast, then test by hand.

The checker avoids false alarms: `alt=""` on decorative images, hidden inputs, submit buttons, fields wrapped in a `<label>` and `aria-label`/`aria-labelledby` are all treated as valid.

---

## ⚙️ Options

| Option | Default | What it does |
|---|---|---|
| `--max-pages N` | 100 | Maximum number of pages to crawl |
| `--workers N` | 10 | Number of parallel requests |
| `--timeout SEC` | 10 | Seconds to wait for each request |
| `--slow SEC` | 2 | Load time above which a page counts as slow |
| `-o, --output PATH` | `site-health-report.html` | Where to save the HTML report |
| `--json PATH` | off | Also save all results as JSON |
| `--min-score N` | off | Exit with code 1 if the accessibility score is below N |
| `--no-fail` | off | Always exit with code 0 |
| `--version` | | Show the version |

```bash
site-health-checker mysite.com --max-pages 500              # bigger crawl ("https://" is added for you)
site-health-checker https://mysite.com --slow 1 -o audit.html  # stricter speed check, custom report name
site-health-checker https://mysite.com --json results.json  # machine-readable output
```

---

## 🔄 Use It in CI/CD

### Option 1: GitHub Action (easiest)

Add this workflow to your repository (for example `.github/workflows/site-health.yml`), with nothing to install:

```yaml
name: Site health
on: pull_request

permissions:
  contents: read
  pull-requests: write   # lets the action comment on the pull request

jobs:
  site-health:
    runs-on: ubuntu-latest
    steps:
      - uses: Reenakotadiya/site-health-checker@v2
        with:
          url: https://staging.mysite.com
          min-score: 90        # optional: fail if the accessibility score drops below 90
```

**What you get on every run:**
- 💬 **A pull request comment** with the accessibility score, broken links and other results. It's updated on each push, never duplicated.
- 📊 **A summary table** on the workflow run page
- 📄 **The full HTML report** saved as a downloadable artifact
- ✅ / ❌ **A pass or fail result** you can use to block merges

`@v2` always points to the latest v2 release, so you get fixes automatically. Pin an exact version like `@v2.1.0` if you prefer.

| Input | Default | What it does |
|---|---|---|
| `url` | (required) | Website to check |
| `max-pages` | 100 | Maximum pages to crawl |
| `min-score` | none | Fail the step if the accessibility score is below this |
| `fail-on-problems` | true | Set to `false` to report without failing the build |
| `comment-on-pr` | true | Post and update one comment on pull requests |
| `upload-report` | true | Save the HTML and JSON reports as an artifact |
| `artifact-name` | `site-health-report` | Artifact name (change it if you use the action twice in one workflow) |
| `report-path` | `site-health-report.html` | Where to save the HTML report |
| `github-token` | `github.token` | Token used for the pull request comment |

**Outputs:** `accessibility-score` and `broken-links`, to use in later steps.

**Ready-made workflows** in [`examples/`](examples/): [check every pull request](examples/pull-request-check.yml) · [check every night](examples/nightly-check.yml) · [check after deploying](examples/after-deploy.yml)

> Pull requests from forks get a read-only token, so the comment is skipped with a warning. The check itself still runs normally.

### Option 2: Any CI tool (GitLab, Jenkins, Azure DevOps, Bitbucket…)

The tool **exits with code 1 when broken links are found, or when the accessibility score drops below `--min-score`**, and with **code 2 if the website can't be loaded at all** (site down, typo in the address), so any pipeline can block a release with it.

With pip:

```bash
pip install site-health-checker
site-health-checker https://staging.mysite.com --min-score 90 --json results.json
```

Or with the Docker image. For example, in **GitLab CI** (`.gitlab-ci.yml`):

```yaml
site-health:
  image:
    name: ghcr.io/reenakotadiya/site-health-checker:2
    entrypoint: [""]
  script:
    - site-health-checker https://staging.mysite.com --min-score 90 -o site-health-report.html
  artifacts:
    when: always
    paths: [site-health-report.html]
```

Docker tags: `latest`, the major version (`2`), or an exact version (`2.1.0`).

---

## 🧠 How It Works

1. Starts at your URL and follows its redirects, so `http://` → `https://` and `www` are handled
2. Crawls every page on the **same domain** (breadth-first, in parallel), up to `--max-pages`
3. **Respects `robots.txt`**, so pages the site asks bots not to visit are skipped
4. Runs the accessibility checks on every HTML page
5. Checks every link found, **internal and external**, once each (`HEAD` first, falling back to `GET` for servers that reject `HEAD`)
6. Writes the HTML report, the JSON output and a console summary

Pages rendered only by JavaScript (single-page apps) are checked as the server sends them.

---

## 🧪 Development

```bash
git clone https://github.com/Reenakotadiya/site-health-checker.git
cd site-health-checker
pip install -e ".[dev]"
pytest
```

Almost 50 tests cover every accessibility rule (including the cases that must **not** be flagged), and a small local website with known problems tests the crawler end to end, with no internet needed.

---

## 🤝 Contributing

Issues and pull requests are welcome! On the roadmap:
- Color contrast checks using a headless browser
- Duplicate IDs, and missing skip-to-content links
- Sitemap.xml support
- A PDF version of the report

---

## 📄 License

[MIT](LICENSE) © Reena Kotadiya

---

## 👩‍💻 Author

**Reena Kotadiya**, QA Automation Engineer

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Reena%20Kotadiya-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/reena-kotadiya-1a7073170)

💬 Questions, ideas or bugs? [Open an issue](https://github.com/Reenakotadiya/site-health-checker/issues).
