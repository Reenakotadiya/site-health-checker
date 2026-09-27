# 🩺 Site Health Checker

[![Tests](https://github.com/Reenakotadiya/site-health-checker/actions/workflows/tests.yml/badge.svg)](https://github.com/Reenakotadiya/site-health-checker/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Audit any website in one command.** Site Health Checker crawls your site and finds the problems that frustrate users and hurt SEO:

- ❌ **Broken links**: 404s, 500s and links that don't respond, plus the page each one appears on
- 🐢 **Slow pages**: pages that take too long to load
- 🖼️ **Images missing alt text**: an accessibility problem for screen reader users
- 🔀 **Redirect chains**: links that bounce through 2+ redirects
- 🏷️ **Missing page titles**: bad for SEO and browser tabs

You get a clean **HTML report** you can share with your team or client, plus optional **JSON** for CI pipelines.

![Sample report](docs/report-screenshot.png)

---

## 🚀 Quick Start

```bash
pip install git+https://github.com/Reenakotadiya/site-health-checker.git

site-health-checker https://example.com
```

Then open `site-health-report.html` in your browser.

```
Checking https://example.com (up to 100 pages)...

Site Health Report for https://example.com/
Crawled 42 pages and checked 318 links in 12.4s

  ✗ Broken links: 3
  ✓ Slow pages: 0
  ✗ Pages with images missing alt: 5
  ✓ Redirect chains: 0
  ✗ Pages missing a title: 1
```

---

## ⚙️ Options

| Option | Default | What it does |
|---|---|---|
| `--max-pages N` | 100 | Maximum number of pages to crawl |
| `--workers N` | 10 | Number of parallel requests |
| `--timeout SEC` | 10 | Seconds to wait for each request |
| `--slow SEC` | 2 | Load time above which a page counts as slow |
| `-o, --output PATH` | `site-health-report.html` | Where to save the HTML report |
| `--json PATH` | off | Also save results as JSON |
| `--no-fail` | off | Exit with code 0 even when broken links are found |
| `--version` | | Show the version |

**Examples**

```bash
site-health-checker mysite.com --max-pages 500              # bigger crawl ("https://" is added for you)
site-health-checker https://mysite.com --slow 1 -o audit.html  # stricter speed check, custom report name
site-health-checker https://mysite.com --json results.json  # machine-readable output
```

---

## 🔄 Use It in CI/CD

The tool **exits with code 1 when broken links are found**, so it can fail a build automatically. Example GitHub Actions step:

```yaml
- name: Check website for broken links
  run: |
    pip install git+https://github.com/Reenakotadiya/site-health-checker.git
    site-health-checker https://staging.mysite.com --json results.json
```

---

## 🧠 How It Works

1. Starts at your URL and follows its redirects, so `http://` → `https://` and `www` are handled
2. Crawls every page on the **same domain** (breadth-first, in parallel), up to `--max-pages`
3. **Respects `robots.txt`**, so pages the site asks bots not to visit are skipped
4. Collects every link on those pages, **internal and external**, and checks each one once (`HEAD` first, falling back to `GET` for servers that reject `HEAD`)
5. Analyzes the results and writes the report

**Good to know**
- `alt=""` is treated as valid, because it's the correct way to mark decorative images. Only images with **no** alt attribute are flagged.
- Links like `mailto:`, `tel:`, `javascript:` and `#anchors` are skipped.
- Pages rendered only by JavaScript (single-page apps) are read as the server sends them.

---

## 🧪 Development

```bash
git clone https://github.com/Reenakotadiya/site-health-checker.git
cd site-health-checker
pip install -e ".[dev]"
pytest
```

The tests spin up a small local website with known problems (a broken link, a redirect chain, a slow page, and so on), so they run in seconds and need no internet.

---

## 🤝 Contributing

Issues and pull requests are welcome! Ideas on the roadmap:
- Check for duplicate titles and meta descriptions
- Detect mixed content (HTTP resources on HTTPS pages)
- Sitemap.xml support

---

## 📄 License

[MIT](LICENSE) © Reena Kotadiya

---

## 👩‍💻 Author

**Reena Kotadiya**, QA Automation Engineer

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Reena%20Kotadiya-0A66C2?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/reena-kotadiya-1a7073170)

💼 Need a website audit or test automation for your project? Let's connect on LinkedIn.
