import json, os, re, hashlib, html, time
from pathlib import Path
from datetime import datetime, timezone
from email.utils import format_datetime
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET
ROOT=Path(__file__).parent
SOURCES=json.loads((ROOT/'sources.json').read_text())
OUT=ROOT/'feeds';OUT.mkdir(exist_ok=True)
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; SuboticaTodayFeedMonitor/1.0; +https://github.com/)'}
S=requests.Session();S.headers.update(HEADERS)
REPORT=[]
def fetch(url):
 r=S.get(url,timeout=18,allow_redirects=True);r.raise_for_status();return r

def discover(soup,base):
 found=[]
 for tag in soup.select('link[rel]'):
  if 'alternate' in (tag.get('rel') or []) and ('rss' in tag.get('type','') or 'atom' in tag.get('type','')):
   found.append(urljoin(base,tag.get('href','')))
 host=f'{urlparse(base).scheme}://{urlparse(base).netloc}'
 for p in ['/feed','/rss','/rss.xml','/feed.xml','/atom.xml','/index.xml']:
  found.append(host+p)
 return list(dict.fromkeys(found))

def valid_feed(content):
 try:
  root=ET.fromstring(content)
  tag=root.tag.lower();return tag.endswith('rss') or tag.endswith('feed') or tag.endswith('rdf')
 except ET.ParseError:return False

def candidates(soup,base):
 host=urlparse(base).netloc.removeprefix('www.')
 container=soup.select_one('main') or soup.select_one('article') or soup.body or soup
 items=[];seen=set()
 for a in container.select('h1 a[href],h2 a[href],h3 a[href],article a[href],.news a[href],.vesti a[href],.post a[href]'):
  href=urljoin(base,a.get('href',''));p=urlparse(href)
  if p.netloc.removeprefix('www.')!=host or href in seen:continue
  title=a.get_text(' ',strip=True)
  if len(title)<18 or len(title)>220 or p.path in ('','/'):continue
  seen.add(href)
  parent=a.find_parent('article') or a.find_parent(class_=re.compile('news|vest|post|item',re.I)) or a.parent
  date=None
  tm=parent.find('time') if parent else None
  if tm:date=tm.get('datetime')
  if not date and parent:
   meta=parent.select_one('[itemprop="datePublished"],meta[property="article:published_time"]')
   if meta:date=meta.get('content')
  if not date:continue # Never invent a publication timestamp
  try:
   dt=datetime.fromisoformat(date.replace('Z','+00:00'))
   if not dt.tzinfo:continue
  except ValueError:continue
  items.append((title,href,dt))
 return items[:80]

def write_rss(src,items):
 rss=ET.Element('rss',version='2.0');ch=ET.SubElement(rss,'channel')
 for k,v in [('title',src['name']),('link',src['url']),('description','Subotica Today monitored source')]:ET.SubElement(ch,k).text=v
 for title,link,dt in sorted(items,key=lambda x:x[2],reverse=True)[:80]:
  it=ET.SubElement(ch,'item');ET.SubElement(it,'title').text=title;ET.SubElement(it,'link').text=link
  ET.SubElement(it,'guid',isPermaLink='true').text=link
  ET.SubElement(it,'pubDate').text=format_datetime(dt.astimezone(timezone.utc))
 ET.indent(rss)
 (OUT/(src['id']+'.xml')).write_bytes(ET.tostring(rss,encoding='utf-8',xml_declaration=True))

def main():
 for src in SOURCES:
  if src['mode']=='existing':
   REPORT.append({'id':src['id'],'status':'existing_feed','url':src['feed']});continue
  if not src.get('url'):
   REPORT.append({'id':src['id'],'status':'needs_url'});continue
  try:
   r=fetch(src['url']);soup=BeautifulSoup(r.text,'html.parser')
   feed=None
   for url in discover(soup,r.url):
    try:
     fr=fetch(url)
     if valid_feed(fr.content):feed=fr.url;break
    except (requests.RequestException,ValueError):pass
   if feed:
    REPORT.append({'id':src['id'],'status':'native_feed_found','url':feed});continue
   items=candidates(soup,r.url)
   if items:
    write_rss(src,items);REPORT.append({'id':src['id'],'status':'generated','count':len(items)})
   else:REPORT.append({'id':src['id'],'status':'needs_custom_parser','reason':'No dated article links extracted; feed NOT fabricated'})
  except requests.RequestException as e:REPORT.append({'id':src['id'],'status':'fetch_failed','error':str(e)[:180]})
  time.sleep(.15)
 (ROOT/'status.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({x['status']:sum(r['status']==x['status'] for r in REPORT) for x in REPORT},ensure_ascii=False))
if __name__=='__main__':main()
