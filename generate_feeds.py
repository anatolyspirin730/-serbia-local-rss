import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from html import unescape
from urllib.parse import urljoin
from xml.dom import minidom


SOURCE_URL = "https://www.subotica.com/vesti"
OUTPUT_FILE = "feeds/subotica.xml"


def download_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SerbiaLocalRSS/1.0)",
            "Accept": "text/html",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return " ".join(value.split())


def extract_articles(html):
    articles = []
    seen = set()

    pattern = re.compile(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(html):
        url = urljoin(SOURCE_URL, unescape(match.group(1)))

        if not re.search(
            r"^https://www\.subotica\.com/vesti/.+-id\d+\.html(?:\?.*)?$",
            url,
            re.IGNORECASE,
        ):
            continue

        title = clean_text(match.group(2))

        if len(title) < 15 or url in seen:
            continue

        seen.add(url)

        articles.append({
            "title": title,
            "url": url,
        })

    return articles


def generate_rss(articles):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Subotica.com — Vesti"
    ET.SubElement(channel, "link").text = SOURCE_URL
    ET.SubElement(channel, "description").text = (
        "Новости Суботицы с сайта Subotica.com"
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

    xml_bytes = ET.tostring(rss, encoding="utf-8")
    return minidom.parseString(xml_bytes).toprettyxml(
        indent="  ",
        encoding="utf-8",
    )


def main():
    print(f"Downloading: {SOURCE_URL}")

    html = download_page(SOURCE_URL)
    articles = extract_articles(html)

    print(f"Articles found: {len(articles)}")

    for article in articles[:5]:
        print(f"- {article['title']}")
        print(f"  {article['url']}")

    if not articles:
        raise RuntimeError(
            "No articles found. RSS file will not be overwritten."
        )

    os.makedirs("feeds", exist_ok=True)

    with open(OUTPUT_FILE, "wb") as file:
        file.write(generate_rss(articles))

    print(f"RSS generated: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
