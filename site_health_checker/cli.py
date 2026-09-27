"""Command-line entry point: site-health-checker https://example.com"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from site_health_checker import __version__
from site_health_checker.crawler import crawl
from site_health_checker.report import analyze, console_summary, to_html, to_json


def _url(value: str) -> str:
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    if not urlparse(value).netloc:
        raise argparse.ArgumentTypeError(f"not a valid website address: {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="site-health-checker",
        description="Audit a website for accessibility problems, broken links, slow pages, redirect chains and missing titles.",
    )
    parser.add_argument("url", type=_url, help="website to check, e.g. https://example.com")
    parser.add_argument("--max-pages", type=int, default=100, help="maximum pages to crawl (default: 100)")
    parser.add_argument("--workers", type=int, default=10, help="parallel requests (default: 10)")
    parser.add_argument("--timeout", type=float, default=10, help="seconds to wait for each request (default: 10)")
    parser.add_argument("--slow", type=float, default=2.0, help="page load time in seconds counted as slow (default: 2)")
    parser.add_argument("-o", "--output", default="site-health-report.html", help="HTML report path")
    parser.add_argument("--json", metavar="PATH", help="also save results as JSON (useful in CI pipelines)")
    parser.add_argument("--min-score", type=int, metavar="N",
                        help="exit with 1 if the accessibility score is below N (for CI pipelines)")
    parser.add_argument("--no-fail", action="store_true", help="always exit with 0, even when problems are found")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    print(f"Checking {args.url} (up to {args.max_pages} pages)...")
    result = crawl(args.url, max_pages=args.max_pages, workers=args.workers, timeout=args.timeout)
    findings = analyze(result, slow_threshold=args.slow)

    Path(args.output).write_text(to_html(result, findings, args.slow), encoding="utf-8")
    if args.json:
        Path(args.json).write_text(to_json(result, findings), encoding="utf-8")

    print(console_summary(result, findings))
    print(f"\nHTML report saved to {Path(args.output).resolve()}")

    # A non-zero exit code lets CI pipelines fail the build.
    too_low = args.min_score is not None and findings.a11y_score is not None and findings.a11y_score < args.min_score
    if too_low:
        print(f"Accessibility score {findings.a11y_score} is below the minimum of {args.min_score}")
    return 1 if (findings.broken_links or too_low) and not args.no_fail else 0


if __name__ == "__main__":
    sys.exit(main())
