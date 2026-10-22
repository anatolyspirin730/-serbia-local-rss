#!/usr/bin/env python3
"""Build an RSS feed from Pannon RTV's Szabadka listing. Never invent publication dates."""
from __future__ import annotations
import email.utils
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element, SubElement, ElementTree
import requests
from bs4 import BeautifulSoup

LISTING = 'https://pannonrtv.com/onkormanyzatok/szabadka'
OUTPUT = Path('feeds/pannon-szabadka.xml')
DATE_RE = re.compile(r'(?<!\d)(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*[;,\s]\s*(\d{1,2}):(\d{2})(?!\d)')

def get_date(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime(*(int(x) for x in m.groups()), tzinfo=timezone.utc)
    except ValueError:
        return None

def main():
    response = requests.get(LISTING, timeout=30, headers={'User-Agent':'Mozilla/5.0 (compatible; LocalRSS/1.0)'})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    # Prefer article cards and dated entries; never assign current time to an undated article.
    candidates = []
    seen = set()
    for heading in soup.select('h2, h3, h4'):
        anchor = heading.find('a', href=True) or heading.find_parent('a', href=True)
        if not anchor:
            continue
        url = urljoin(LISTING, anchor['href']).split('#')[0]
        parsed = urlparse(url)
        if parsed.netloc not in {'pannonrtv.com','www.pannonrtv.com'} or url == LISTING or url in seen:
            continue
        title = heading.get_text(' ', strip=True)
        if len(title) < 12:
            continue
        parent = heading
        published = None
        for _ in range(4):
            parent = parent.parent
            if parent is None:
                break
            # Avoid grabbing a date from a whole listing; inspect local card only.
            txt = parent.get_text(' ', strip=True)
            if len(txt) > 1400:
                break
            published = get_date(txt)
            if published:
                break
        if not published:
            continue
        seen.add(url)
        candidates.append((published, title, url))
    if not candidates:
        raise RuntimeError('No dated article cards found. Refusing to publish an empty or fabricated RSS feed.')
    candidates.sort(reverse=True)
    rss = Element('rss', {'version':'2.0'})
    channel = SubElement(rss, 'channel')
    for tag, value in [('title','Pannon RTV — Szabadka'),('link',LISTING),('description','Szabadka local news from Pannon RTV')]:
        SubElement(channel,tag).text=value
    for published,title,url in candidates[:60]:
        item=SubElement(channel,'item')
        for tag,value in [('title',title),('link',url),('guid',url),('pubDate',email.utils.format_datetime(published))]:
            SubElement(item,tag).text=value
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    ElementTree(rss).write(OUTPUT,encoding='utf-8',xml_declaration=True)
    print(f'Wrote {len(candidates[:60])} dated articles to {OUTPUT}')

if __name__=='__main__':
    main()
