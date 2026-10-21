import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import format_datetime
from html import unescape
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.dom import minidom


SOURCES = [
    {
        "name": "Subotica.com — Vesti",
        "url": "https://www.subotica.com/vesti",
        "file": "feeds/subotica.xml",
        "kind": "subotica",
    },
    {
        "name": "Subotičke — Vesti",
        "url": "https://suboticke.rs/tema/srbija/vesti/",
        "file": "feeds/suboticke-vesti.xml",
        "kind": "suboticke",
    },
    {
        "name": "Subotičke — Servisne informacije",
        "url": "https://suboticke.rs/tema/subotica/servisne-informacije/",
        "file": "feeds/suboticke-servis.xml",
        "kind": "suboticke",
    },
    {
        "name": "Subotičke — Hronika",
        "url": "https://suboticke.rs/tema/subotica/hronika/",
        "file": "feeds/suboticke-hronika.xml",
        "kind": "suboticke",
    },
    {
        "name": "Subotičke — Sport",
        "url": "https://suboticke.rs/tema/subotica/sport-subotica/",
        "file": "feeds/suboticke-sport.xml",
        "kind": "suboticke",
    },
]


CACHE_FILE = "feeds/publication_dates.json"
MAX_WORKERS = 6

ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>',
    re.IGNORECASE | re.DOTALL,
)

HEADING_RE = re.compile(
    r'<h[1-6]\b([^>]*)>(.*?)</h[1-6]\s*>',
    re.IGNORECASE | re.DOTALL,
)

DATE_PATTERNS = {
    "subotica": [
        re.compile(
            r'"datePublished"\s*:\s*"([^"]+)"',
            re.IGNORECASE,
        ),
    ],
    "suboticke": [
        re.compile(
            r'<meta\b(?=[^>]*\bproperty\s*=\s*["\']article:published_time["\'])'
            r'[^>]*\bcontent\s*=\s*["\']([^"\']+)',
            re.IGNORECASE,
        ),
        re.compile(
            r'"datePublished"\s*:\s*"([^"]+)"',
            re.IGNORECASE,
        ),
    ],
}


def download_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return " ".join(value.split())


def canonical_url(href, base):
    url = urljoin(base, unescape(href).strip())
    parts = urlsplit(url)

    if parts.scheme not in ("http", "https"):
        return None

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc.lower(),
            parts.path,
            "",
            "",
        )
    )


def extract_subotica(html, source):
    articles = []
    seen = set()

    for match in ANCHOR_RE.finditer(html):
        url = canonical_url(match.group(1), source["url"])

        if not url:
            continue

        if not re.fullmatch(
            r"https://www\.subotica\.com/vesti/.+-id\d+\.html",
            url,
            re.IGNORECASE,
        ):
            continue

        title = clean_text(match.group(2))

        if len(title) < 15 or url in seen:
            continue

        seen.add(url)
        articles.append({"title": title, "url": url})

    return articles


def extract_suboticke(html, source):
    articles = []
    seen = set()

    for heading in HEADING_RE.finditer(html):
        attrs = heading.group(1)

        if not re.search(r"\bentry-title\b", attrs, re.IGNORECASE):
            continue

        if not re.search(r"\btd-module-title\b", attrs, re.IGNORECASE):
            continue

        anchor = ANCHOR_RE.search(heading.group(2))

        if not anchor:
            continue

        url = canonical_url(anchor.group(1), source["url"])

        if not url:
            continue

        parts = urlsplit(url)

        if parts.hostname not in ("suboticke.rs", "www.suboticke.rs"):
            continue

        if parts.path in ("", "/") or parts.path.startswith("/tema/"):
            continue

        title = clean_text(anchor.group(2))

        if len(title) < 15 or url in seen:
            continue

        seen.add(url)
        articles.append({"title": title, "url": url})

    return articles


def parse_date(value):
    try:
        value = unescape(value).strip()

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        parsed = datetime.fromisoformat(value)

        if parsed.tzinfo is None:
            return None

        return parsed.isoformat()

    except (ValueError, TypeError):
        return None


def extract_publication_date(html, kind):
    for pattern in DATE_PATTERNS[kind]:
        for match in pattern.finditer(html):
            result = parse_date(match.group(1))

            if result:
                return result

    return None


def fetch_article_date(article_url, kind):
    try:
        html = download_page(article_url)
        return extract_publication_date(html, kind)

    except Exception as exc:
        print(
            f"DATE WARNING: {article_url}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return None


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {}

        return {
            url: date
            for url, date in data.items()
            if isinstance(url, str)
            and isinstance(date, str)
            and parse_date(date)
        }

    except (OSError, ValueError) as exc:
        print(f"CACHE WARNING: {exc}", file=sys.stderr)
        return {}


def save_cache(cache):
    temporary_file = CACHE_FILE + ".tmp"

    with open(temporary_file, "w", encoding="utf-8") as file:
        json.dump(
            cache,
            file,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        file.write("\n")

    os.replace(temporary_file, CACHE_FILE)


def generate_rss(articles, source):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = source["name"]
    ET.SubElement(channel, "link").text = source["url"]
    ET.SubElement(channel, "description").text = (
        "Новости: " + source["name"]
    )
    ET.SubElement(channel, "language").text = "sr"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )

    for article in articles:
        item = ET.SubElement(channel, "item")

        ET.SubElement(item, "title").text = article["title"]
        ET.SubElement(item, "link").text = article["url"]
        ET.SubElement(
            item,
            "guid",
            isPermaLink="true",
        ).text = article["url"]

        publication_date = article.get("publication_date")

        if publication_date:
            parsed = datetime.fromisoformat(publication_date)
            ET.SubElement(item, "pubDate").text = format_datetime(parsed)

    xml_bytes = ET.tostring(rss, encoding="utf-8")

    return minidom.parseString(xml_bytes).toprettyxml(
        indent="  ",
        encoding="utf-8",
    )


def main():
    os.makedirs("feeds", exist_ok=True)

    cache = load_cache()
    successful = 0
    failures = []
    pending_sources = []
    articles_to_fetch = {}

    # Этап 1: собираем статьи из всех пяти разделов.
    for source in SOURCES:
        print(f"\n=== {source['name']} ===", flush=True)

        try:
            html = download_page(source["url"])

            if source["kind"] == "subotica":
                articles = extract_subotica(html, source)
            else:
                articles = extract_suboticke(html, source)

            print(f"Articles found: {len(articles)}", flush=True)

            if not articles:
                raise ValueError(
                    "No articles extracted; existing RSS retained"
                )

            pending_sources.append((source, articles))

            for article in articles:
                url = article["url"]

                if url not in cache:
                    articles_to_fetch[url] = source["kind"]

        except Exception as exc:
            failures.append((source["name"], str(exc)))

            print(
                f"WARNING: {exc}; previous RSS retained if present",
                file=sys.stderr,
                flush=True,
            )

    # Этап 2: загружаем только статьи без сохранённой даты.
    print(
        f"\nUnique articles requiring date lookup: "
        f"{len(articles_to_fetch)}",
        flush=True,
    )

    dates_found = 0
    dates_missing = 0

    if articles_to_fetch:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(fetch_article_date, url, kind): url
                for url, kind in articles_to_fetch.items()
            }

            for future in as_completed(futures):
                url = futures[future]

                try:
                    publication_date = future.result()
                except Exception as exc:
                    publication_date = None
                    print(
                        f"DATE ERROR: {url}: {exc}",
                        file=sys.stderr,
                        flush=True,
                    )

                if publication_date:
                    cache[url] = publication_date
                    dates_found += 1
                else:
                    dates_missing += 1

    print(
        f"Date lookup: {dates_found} found, "
        f"{dates_missing} missing",
        flush=True,
    )

    # Этап 3: записываем RSS.
    for source, articles in pending_sources:
        for article in articles:
            article["publication_date"] = cache.get(article["url"])

        with_dates = sum(
            1 for article in articles if article["publication_date"]
        )

        try:
            xml = generate_rss(articles, source)

            with open(source["file"], "wb") as output:
                output.write(xml)

            print(
                f"\nRSS saved: {source['file']}",
                flush=True,
            )
            print(
                f"Publication dates: {with_dates}/{len(articles)}",
                flush=True,
            )

            for article in articles[:3]:
                print(f"  {article['title']}")
                print(f"  {article['url']}")
                print(
                    f"  Date: "
                    f"{article['publication_date'] or 'NOT FOUND'}"
                )

            successful += 1

        except Exception as exc:
            failures.append((source["name"], str(exc)))

            print(
                f"WARNING: {exc}; previous RSS retained if present",
                file=sys.stderr,
                flush=True,
            )

    # Этап 4: сохраняем кэш дат.
    save_cache(cache)

    print(
        f"\nRESULT: {successful}/{len(SOURCES)} "
        f"sources updated; {len(failures)} failures",
        flush=True,
    )

    print(
        f"DATE CACHE: {len(cache)} articles",
        flush=True,
    )

    for name, error in failures:
        print(f"FAILED: {name}: {error}")

    if successful == 0:
        raise RuntimeError(
            "All sources failed. No RSS files updated."
        )


if __name__ == "__main__":
    main()
