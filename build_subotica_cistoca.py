#!/usr/bin/env python3
"""Standalone Čistoća i zelenilo RSS builder. Preserves other feeds."""
import re,json,hashlib,html
from pathlib import Path
from datetime import datetime,timezone
from email.utils import format_datetime
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from xml.etree.ElementTree import Element,SubElement,ElementTree
BASE=Path('feeds'); BASE.mkdir(exist_ok=True)
AUD=Path('audit-results'); AUD.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; SuboticaLocalRSS/2.0)','Accept-Language':'sr-RS,sr;q=0.9,en;q=0.6'})
DATE=re.compile(r'(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d\d)(?!\d)')
URLS={'cistoca':'https://www.cistoca-su.co.rs/lat/vesti/'}
REPORT={}
def date_of(s):
 m=DATE.search(s or '')
 if not m:return None
 try:return datetime(int(m[3]),int(m[2]),int(m[1]),tzinfo=timezone.utc)
 except ValueError:return None
def fetch(url):
 r=S.get(url,timeout=25);r.raise_for_status();return r
def add(items,title,url,date,desc=''):
 if not title or not url or not date:return
 if date.year<2020 or date>datetime.now(timezone.utc):return
 items[url]={'title':title.strip()[:220],'link':url,'date':date,'description':desc.strip()[:800]}
def cistoca(soup,base):
 out={}
 # Dates are explicitly displayed in news listing; tie each date to its local card/link.
 for a in soup.select('a[href]'):
  href=urljoin(base,a['href']);label=a.get_text(' ',strip=True)
  if not href.startswith('https://www.cistoca-su.co.rs/') or len(label)<12:continue
  for block in [a.parent,a.parent.parent if a.parent else None]:
   if block is None:continue
   txt=block.get_text(' ',strip=True)
   match=DATE.search(txt[:180])
   if match and len(txt)<1800:
    d=date_of(match.group(0)); title=DATE.sub('',label,count=1).strip(' .-')
    if len(title)<12:title=DATE.sub('',txt,count=1).strip(' .-')[:160]
    add(out,title,href,d,txt);break
 return out
def write(name,items):
 if not items:return None
 root=Element('rss',version='2.0');ch=SubElement(root,'channel')
 for k,v in [('title','Subotica — '+name),('link',URLS[name]),('description','Verified source-specific feed')]:SubElement(ch,k).text=v
 for it in sorted(items.values(),key=lambda x:x['date'],reverse=True)[:80]:
  node=SubElement(ch,'item')
  for k,v in [('title',it['title']),('link',it['link']),('guid',it['link']),('pubDate',format_datetime(it['date'])),('description',it['description'])]:SubElement(node,k).text=v
 target=BASE/('special-'+name+'.xml');ElementTree(root).write(target,encoding='utf-8',xml_declaration=True);return str(target)
name='cistoca'
url=URLS[name]
info={'url':url,'status':'unknown','count':0,'samples':[]}
try:
 r=fetch(url);soup=BeautifulSoup(r.content,'html.parser')
 items=cistoca(soup,r.url)
 info['http_status']=r.status_code
 info['count']=len(items)
 info['output']=write(name,items)
 info['status']='feed_created' if items else 'no_verified_items_existing_feed_preserved'
 info['samples']=[{'title':v['title'],'url':v['link'],'date':v['date'].isoformat()} for v in list(items.values())[:5]]
except Exception as e:
 info['status']='fetch_error_existing_feed_preserved';info['error']=str(e)[:400]
REPORT[name]=info
print(name,info['status'],info['count'])
(AUD/'cistoca_report.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf8')
