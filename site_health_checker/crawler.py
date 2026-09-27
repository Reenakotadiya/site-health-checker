"""Crawl a website and check every link it contains."""
from __future__ import annotations

import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from site_health_checker import __version__

USER_AGENT = f"site-health-checker/{__version__} (+https://github.com/Reenakotadiya/site-health-checker)"
SKIPPED_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "#")


@dataclass
class PageResult:
    url: str
    status: int | None
    load_time: float
    is_html: bool = False
    title: str = ""
    images_missing_alt: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class LinkResult:
    url: str
    status: int | None = None  # None means the request itself failed
    error: str = ""
    redirects: list[str] = field(default_factory=list)  # every hop before the final URL
    final_url: str = ""
    found_on: set[str] = field(default_factory=set)

    @property
    def broken(self) -> bool:
        return self.status is None or self.status >= 400


@dataclass
class CrawlResult:
    start_url: str
    pages: list[PageResult]
    links: list[LinkResult]
    duration: float


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []
        self.images_missing_alt: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href"):
            self.hrefs.append(attrs["href"])
        elif tag == "img" and "alt" not in attrs:
            # alt="" is valid for decorative images, so only a missing attribute is flagged.
            self.images_missing_alt.append(attrs.get("src") or "(no src)")
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def normalize(base_url: str, href: str) -> str | None:
    """Absolute http(s) URL without the #fragment, or None for links we don't check."""
    href = href.strip()
    if not href or href.lower().startswith(SKIPPED_SCHEMES):
        return None
    url, _ = urldefrag(urljoin(base_url, href))
    return url if urlparse(url).scheme in ("http", "https") else None


def _load_robots(start_url: str, session: requests.Session, timeout: float) -> RobotFileParser | None:
    robots_url = urljoin(start_url, "/robots.txt")
    try:
        response = session.get(robots_url, timeout=timeout)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    parser = RobotFileParser(robots_url)
    parser.parse(response.text.splitlines())
    return parser


def _fetch_page(session: requests.Session, url: str, timeout: float) -> tuple[PageResult, str, list[str]]:
    """Return the page result, its final URL after redirects, and the raw hrefs on it."""
    started = time.perf_counter()
    try:
        response = session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return PageResult(url, None, time.perf_counter() - started, error=type(exc).__name__), url, []
    load_time = time.perf_counter() - started

    page = PageResult(url, response.status_code, load_time)
    page.is_html = "html" in response.headers.get("Content-Type", "")
    if not page.is_html or response.status_code >= 400:
        return page, response.url, []

    parser = _PageParser()
    parser.feed(response.text)
    page.title = " ".join(parser.title.split())
    page.images_missing_alt = parser.images_missing_alt
    return page, response.url, parser.hrefs


def check_link(session: requests.Session, link: LinkResult, timeout: float) -> LinkResult:
    """Fill in status and redirect hops. HEAD first, GET when the server refuses HEAD."""
    try:
        response = session.head(link.url, timeout=timeout, allow_redirects=True)
        if response.status_code in (403, 405, 501):
            response = session.get(link.url, timeout=timeout, allow_redirects=True, stream=True)
            response.close()
    except requests.RequestException as exc:
        link.error = type(exc).__name__
        return link
    link.status = response.status_code
    link.redirects = [hop.url for hop in response.history]
    link.final_url = response.url
    return link


def crawl(start_url: str, max_pages: int = 100, workers: int = 10, timeout: float = 10) -> CrawlResult:
    """Crawl pages on the start URL's domain, then check every link found (internal and external)."""
    started = time.perf_counter()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    try:
        # Follow the start URL's own redirects (http -> https, example.com -> www.example.com)
        # so the crawl stays on the domain the site actually lives on.
        start_url = session.head(start_url, timeout=timeout, allow_redirects=True).url
    except requests.RequestException:
        pass  # _fetch_page will record the error for the start page
    domain = urlparse(start_url).netloc
    robots = _load_robots(start_url, session, timeout)

    pages: dict[str, PageResult] = {}
    links: dict[str, LinkResult] = {}
    queue, queued = deque([start_url]), {start_url}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        while queue and len(pages) < max_pages:
            batch = [queue.popleft() for _ in range(min(len(queue), max_pages - len(pages)))]
            batch = [url for url in batch if robots is None or robots.can_fetch(USER_AGENT, url)]
            for page, final_url, hrefs in pool.map(lambda u: _fetch_page(session, u, timeout), batch):
                if urlparse(final_url).netloc != domain or final_url in pages:
                    continue  # redirected off-site, or to a page we already have
                pages[final_url] = page
                for href in hrefs:
                    url = normalize(final_url, href)
                    if url is None:
                        continue
                    links.setdefault(url, LinkResult(url)).found_on.add(final_url)
                    if urlparse(url).netloc == domain and url not in queued:
                        queued.add(url)
                        queue.append(url)

        # Pages we fetched directly already have a status; only check the rest.
        for url, link in links.items():
            if url in pages:
                link.status, link.error = pages[url].status, pages[url].error
        unchecked = [link for url, link in links.items() if url not in pages]
        list(pool.map(lambda link: check_link(session, link, timeout), unchecked))

    return CrawlResult(start_url, list(pages.values()), list(links.values()), time.perf_counter() - started)
