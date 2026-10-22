#!/usr/bin/env python3
"""Pannon RTV RSS-based Szabadka and local utility notices. Conservative keyword filtering.
Source is the public RSS endpoint; this does not claim complete section coverage.
"""
from __future__ import annotations
import email.utils
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

SOURCE = 'https://pannonrtv.com/feed'
CITY = re.compile(r'(?i)szabadk\w*|subotic\w*|palics\w*|pali[cć]\w*|csantav[eé]r\w*|\bčantavir\b|\bbajmok\b|\bbajmak\b|\btavankut\b|\bkelebi\w*|\bhajdukovo\b|\bludas\b|\b[lL]udaš\b|\b\u0161upljak\b|\b\u017eednik\b|\b\u017eednik\b|\b\u0111ur\u0111in\b|\b\u0111ur\u0111in\b')
UTILITY = re.compile(r'(?i)\u00e1ramsz\u00fcnet|\u00e1ramkimarad|villany|v\u00edzhi\u00e1ny|v\u00edzsz\u00fcnet|v\u00edzell\u00e1t\u00e1s|v\u00edzvezet\u00e9k|hullad\u00e9k|szem\u00e9tsz\u00e1ll\u00edt|t\u00e1vf\u0171t|f\u0171t\u00e9s|g\u00e1zell\u00e1t|\u00fatlez\u00e1r|\u00fatburkol|forgalomkorl\u00e1toz|k\u00f6zm\u0171|isklju\u010denj|nestanak struje|bez vode|vodovod|grejanje|odvoz sme\u0107a|obustava saobra\u0107aja|radovi na putu')
NS = {'atom':'http://www.w3.org/2005/Atom', 'dc':'http://purl.org/dc/elements/1.1/', 'content':'http://purl.org/rss/1.0/modules/content/'}

def value(node, name):
    e = node.find(name, NS)
    return ''.join(e.itertext()).strip() if e is not None else ''

def read_items(data):
    root = ET.fromstring(data)
    if root.tag.endswith('rss') or root.find('channel') is not None:
        for item in root.findall('./channel/item'):
            title = value(item,'title'); link=value(item,'link'); date=value(item,'pubDate') or value(item,'dc:date')
            desc=value(item,'description'); cats=' '.join(value(x,'') for x in [])
            cats=' '.join((x.text or '') for x in item.findall('category'))
            if not date: continue
            try:
                d=email.utils.parsedate_to_datetime(date)
                if d is None: d=datetime.fromisoformat(date.replace('Z','+00:00'))
                if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
            except (ValueError,TypeError): continue
            yield {'title':title,'link':link,'date':d,'description':desc,'categories':cats}
    else:
        for item in root.findall('atom:entry',NS):
            title=value(item,'atom:title'); date=value(item,'atom:published') or value(item,'atom:updated')
            links=[x.get('href','') for x in item.findall('atom:link',NS) if x.get('rel','alternate')=='alternate']
            if not links or not date:continue
            try:d=datetime.fromisoformat(date.replace('Z','+00:00'))
            except ValueError:continue
            yield {'title':title,'link':links[0],'date':d,'description':value(item,'atom:summary'),'categories':' '.join(x.get('term','') for x in item.findall('atom:category',NS))}

def write_feed(path,title,items):
    if not items:
        print(f'WARNING: 0 matching items for {path}; keeping any existing file unchanged')
        return
    rss=ET.Element('rss',version='2.0');ch=ET.SubElement(rss,'channel')
    for key,text in [('title',title),('link',SOURCE),('description','Pannon RTV: keyword-filtered local articles from the public RSS; coverage is not exhaustive')]:
        ET.SubElement(ch,key).text=text
    for obj in sorted(items,key=lambda x:x['date'],reverse=True):
        el=ET.SubElement(ch,'item')
        for key,text in [('title',obj['title']),('link',obj['link']),('guid',obj['link']),('pubDate',email.utils.format_datetime(obj['date'])),('description',obj['description'])]:
            ET.SubElement(el,key).text=text
    path.parent.mkdir(parents=True,exist_ok=True)
    ET.ElementTree(rss).write(path,encoding='utf-8',xml_declaration=True)
    print(f'OK: {path} => {len(items)} articles')

def main():
    r=requests.get(SOURCE,headers={'User-Agent':'Mozilla/5.0 (compatible; SuboticaLocalNews/1.0; RSS reader)','Accept':'application/rss+xml, application/xml;q=0.9, */*;q=0.5'},timeout=25)
    r.raise_for_status()
    entries=list(read_items(r.content))
    if not entries:raise RuntimeError('Source RSS contained no parseable dated articles; keeping old output')
    entries=[x for x in entries if x['title'] and x['link'] and urlparse(x['link']).hostname in ('pannonrtv.com','www.pannonrtv.com')]
    city=[x for x in entries if CITY.search(' '.join([x['title'],x['description'],x['categories']]))]
    service=[x for x in city if UTILITY.search(' '.join([x['title'],x['description'],x['categories']]))]
    print(f'Fetched {len(entries)} Pannon articles; local keyword matches {len(city)}; local service notices {len(service)}')
    write_feed(Path('feeds/pannon-szabadka.xml'),'Pannon RTV — Szabadka (RSS keyword matches)',city)
    write_feed(Path('feeds/pannon-szabadka-service.xml'),'Pannon RTV — Szabadka utilities (RSS keyword matches)',service)

if __name__=='__main__':main()
