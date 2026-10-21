import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

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


ANCHOR_RE = re.compile(
    r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a\s*>',
    re.IGNORECASE | re.DOTALL,
)

HEADING_RE = re.compile(
    r'<h[1-6]\b([^>]*)>(.*?)</h[1-6]\s*>',
    re.IGNORECASE | re.DOTALL,
)


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

        return response.read().decode(
            charset,
            errors="replace",
        )


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
        url = canonical_url(
            match.group(1),
            source["url"],
        )

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

        articles.append(
            {
                "title": title,
                "url": url,
            }
        )

    return articles


def extract_suboticke(html, source):
    articles = []
    seen = set()

    for heading in HEADING_RE.finditer(html):
        attrs = heading.group(1)

        if not re.search(
            r"\bentry-title\b",
            attrs,
            re.IGNORECASE,
        ):
            continue

        if not re.search(
            r"\btd-module-title\b",
            attrs,
            re.IGNORECASE,
        ):
            continue

        anchor = ANCHOR_RE.search(
            heading.group(2)
        )

        if not anchor:
            continue

        url = canonical_url(
            anchor.group(1),
            source["url"],
        )

        if not url:
            continue

        parts = urlsplit(url)

        if parts.hostname not in (
            "suboticke.rs",
            "www.suboticke.rs",
        ):
            continue

        if parts.path in ("", "/"):
            continue

        if parts.path.startswith("/tema/"):
            continue

        title = clean_text(
            anchor.group(2)
        )

        if len(title) < 15:
            continue

        if url in seen:
            continue

        seen.add(url)

        articles.append(
            {
                "title": title,
                "url": url,
            }
        )

    return articles


def generate_rss(articles, source):
    rss = ET.Element(
        "rss",
        version="2.0",
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = source["name"]

    ET.SubElement(
        channel,
        "link",
    ).text = source["url"]

    ET.SubElement(
        channel,
        "description",
    ).text = "Новости: " + source["name"]

    ET.SubElement(
        channel,
        "language",
    ).text = "sr"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(timezone.utc)
    )

    for article in articles:
        item = ET.SubElement(
            channel,
            "item",
        )

        ET.SubElement(
            item,
            "title",
        ).text = article["title"]

        ET.SubElement(
            item,
            "link",
        ).text = article["url"]

        ET.SubElement(
            item,
            "guid",
            isPermaLink="true",
        ).text = article["url"]

    xml_bytes = ET.tostring(
        rss,
        encoding="utf-8",
    )

    return minidom.parseString(
        xml_bytes
    ).toprettyxml(
        indent="  ",
        encoding="utf-8",
    )


def main():
    successful = 0
    failures = []

    os.makedirs(
        "feeds",
        exist_ok=True,
    )

    for source in SOURCES:
        print(
            f"\n=== {source['name']} ===",
            flush=True,
        )

        try:
            html = download_page(
                source["url"]
            )

            if source["kind"] == "subotica":
                articles = extract_subotica(
                    html,
                    source,
                )
            else:
                articles = extract_suboticke(
                    html,
                    source,
                )

            print(
                f"Articles found: {len(articles)}",
                flush=True,
            )

            if not articles:
                raise ValueError(
                    "No articles extracted; "
                    "existing RSS retained"
                )

            xml = generate_rss(
                articles,
                source,
            )

            with open(
                source["file"],
                "wb",
            ) as output:
                output.write(xml)

            print(
                f"RSS saved: {source['file']}",
                flush=True,
            )

            for article in articles[:3]:
                print(
                    f"  {article['title']}"
                )
                print(
                    f"  {article['url']}"
                )

            successful += 1

        except Exception as exc:
            failures.append(
                (
                    source["name"],
                    str(exc),
                )
            )

            print(
                f"WARNING: {exc}; "
                "previous RSS retained if present",
                file=sys.stderr,
                flush=True,
            )

    print(
        f"\nRESULT: {successful}/{len(SOURCES)} "
        f"sources updated; "
        f"{len(failures)} failures"
    )

    for name, error in failures:
        print(
            f"FAILED: {name}: {error}"
        )

    if successful == 0:
        raise RuntimeError(
            "All sources failed. "
            "No RSS files updated."
        )


if __name__ == "__main__":
    main()
