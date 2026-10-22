"""Subotica RSS source audit + conservative feed generator (v3).
No fabricated dates; no global TLS verification bypass.
"""
import json, re, time, hashlib
from pathlib import Path
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SOURCES = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
OUT = ROOT / 'feeds'
OUT.mkdir(exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; SuboticaTodayFeedMonitor/2.0)', 'Accept': 'text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8'})
REPORT = []
TIMEOUT = (8, 20)


def fetch(url):
    response = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response


def parse_feed(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    name = root.tag.rsplit('}', 1)[-1].lower()
    if name not in ('rss', 'feed', 'rdf'):
        return None
    entries = root.findall('.//item') if name != 'feed' else root.findall('{http://www.w3.org/2005/Atom}entry')
    if name == 'feed' and not entries:
        entries = root.findall('entry')
    return {'format': name, 'items': len(entries)}


def feed_urls(soup, base):
    urls = []
    for link in soup.find_all('link', href=True):
        rel = link.get('rel') or []
        typ = (link.get('type') or '').lower()
        if 'alternate' in rel and any(x in typ for x in ('rss', 'atom', 'xml')):
            urls.append(urljoin(base, link['href']))
    for a in soup.select('a[href]'):
        href = a['href']
        if re.search(r'(?i)(?:/feed/?$|/rss(?:\.xml|/?$)|format=feed|atom\.xml)', href):
            urls.append(urljoin(base, href))
    p = urlparse(base)
    host = f'{p.scheme}://{p.netloc}'
    urls.extend(host + path for path in ('/feed/', '/rss/', '/rss.xml', '/feed.xml', '/atom.xml', '/index.php?format=feed&type=rss'))
    return list(dict.fromkeys(urls))[:20]


def parse_date(raw):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).strip().replace('Z', '+00:00'))
    except (ValueError, TypeError):
        try:
            dt = parsedate_to_datetime(str(raw))
        except (ValueError, TypeError, IndexError):
            return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc)


def extract_items(soup, base):
    hostname = urlparse(base).netloc.removeprefix('www.')
    container = soup.select_one('main') or soup.body or soup
    results = {}
    for a in container.select('article a[href], h2 a[href], h3 a[href], .news a[href], .vesti a[href], .post a[href]'):
        href = urljoin(base, a['href']).split('#')[0]
        parsed = urlparse(href)
        if parsed.scheme not in ('https', 'http') or parsed.netloc.removeprefix('www.') != hostname:
            continue
        title = a.get_text(' ', strip=True)
        if not 18 <= len(title) <= 220 or parsed.path in ('', '/'):
            continue
        parent = a.find_parent('article') or a.find_parent(class_=re.compile('news|vest|post|item', re.I)) or a.parent
        raw = None
        if parent:
            tag = parent.find('time')
            if tag:
                raw = tag.get('datetime') or tag.get('content')
            if not raw:
                meta = parent.select_one('[itemprop="datePublished"], meta[property="article:published_time"], meta[name="date"]')
                if meta:
                    raw = meta.get('content') or meta.get('datetime')
        dt = parse_date(raw)
        if dt and href not in results:
            results[href] = (title, href, dt)
    return sorted(results.values(), key=lambda item: item[2], reverse=True)[:80]


def save_rss(source, items):
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in (('title', source['name']), ('link', source['url']), ('description', 'Subotica Today monitored source')):
        ET.SubElement(channel, key).text = value
    for title, url, dt in items:
        entry = ET.SubElement(channel, 'item')
        for key, value in (('title', title), ('link', url), ('guid', url), ('pubDate', format_datetime(dt))):
            ET.SubElement(entry, key).text = value
    ET.indent(rss)
    path = OUT / (source['id'] + '.xml')
    path.write_bytes(ET.tostring(rss, encoding='utf-8', xml_declaration=True))
    return path


def probe_feed_without_homepage(source):
    """A 403/SSL error on the homepage must not prevent checking public RSS endpoints."""
    base = source.get('url')
    if not base:
        return None
    parsed = urlparse(base)
    host = f'{parsed.scheme}://{parsed.netloc}'
    urls = [host + path for path in ('/feed/', '/feed', '/rss/', '/rss.xml', '/feed.xml', '/atom.xml', '/index.php?format=feed&type=rss')]
    # Try common WordPress category feeds only when category URLs are explicitly supplied.
    for section in source.get('sections', []):
        urls.append(urljoin(base, section.rstrip('/') + '/feed/'))
    for candidate in dict.fromkeys(urls):
        try:
            r = fetch(candidate)
            parsed_feed = parse_feed(r.content)
            if parsed_feed and parsed_feed['items']:
                return {'id': source['id'], 'status': 'native_feed_verified', 'url': r.url, 'feed': parsed_feed, 'discovery': 'direct_feed_probe'}
        except requests.RequestException:
            continue
    return None


def failure_with_feed_fallback(source, failure):
    found = probe_feed_without_homepage(source)
    return found if found else failure


def check(source):
    sid = source['id']
    if source.get('mode') == 'existing':
        url = source.get('feed')
        if not url:
            return {'id': sid, 'status': 'existing_feed_missing_url'}
        try:
            response = fetch(url)
            feed = parse_feed(response.content)
            return {'id': sid, 'status': 'existing_feed_verified' if feed and feed['items'] else 'existing_feed_empty_or_invalid', 'url': response.url, 'feed': feed}
        except requests.RequestException as exc:
            return {'id': sid, 'status': 'existing_feed_fetch_failed', 'url': url, 'error': str(exc)[:300]}
    url = source.get('url')
    if not url:
        return {'id': sid, 'status': 'needs_url'}
    try:
        response = fetch(url)
    except requests.exceptions.SSLError as exc:
        return failure_with_feed_fallback(source, {'id': sid, 'status': 'ssl_error', 'url': url, 'error': str(exc)[:300]})
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else None
        return failure_with_feed_fallback(source, {'id': sid, 'status': 'http_error', 'http_status': code, 'url': url, 'error': str(exc)[:300]})
    except requests.RequestException as exc:
        return failure_with_feed_fallback(source, {'id': sid, 'status': 'fetch_failed', 'url': url, 'error': str(exc)[:300]})
    direct = parse_feed(response.content)
    if direct:
        return {'id': sid, 'status': 'native_feed_verified' if direct['items'] else 'native_feed_empty', 'url': response.url, 'feed': direct}
    soup = BeautifulSoup(response.content, 'html.parser')
    empty = []
    for feed_url in feed_urls(soup, response.url):
        try:
            feed_response = fetch(feed_url)
            parsed = parse_feed(feed_response.content)
            if parsed and parsed['items']:
                return {'id': sid, 'status': 'native_feed_verified', 'url': feed_response.url, 'feed': parsed}
            if parsed:
                empty.append({'url': feed_response.url, 'format': parsed['format']})
        except requests.RequestException:
            pass
    items = extract_items(soup, response.url)
    if items:
        path = save_rss(source, items)
        return {'id': sid, 'status': 'generated', 'url': f'feeds/{path.name}', 'items': len(items)}
    return {'id': sid, 'status': 'needs_custom_parser', 'empty_feeds': empty, 'reason': 'No trustworthy dated articles found; no feed fabricated', 'next_action': 'site-specific parser or official alternate source required'}


def main():
    for source in SOURCES:
        try:
            result = check(source)
        except Exception as exc:
            result = {'id': source['id'], 'status': 'unexpected_error', 'error': str(exc)[:300]}
        REPORT.append(result)
        print(f"{result['id']}: {result['status']}", flush=True)
        time.sleep(0.1)
    (ROOT / 'status.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {status: sum(item['status'] == status for item in REPORT) for status in sorted(set(item['status'] for item in REPORT))}
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
