#!/usr/bin/env python3
"""Conservative RSS builder and diagnostic for unresolved Subotica sources.
Never invent publication dates. Never delete/overwrite a working feed with empty output.
"""
import os,re,json,hashlib,logging
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime,format_datetime
from urllib.parse import urljoin,urlsplit,urlunsplit
from xml.etree.ElementTree import Element,SubElement,ElementTree,fromstring
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

SOURCES=json.load(open('final7_sources.json',encoding='utf8'))
NOW=datetime.now(timezone.utc)
HEAD={'User-Agent':'Mozilla/5.0 (compatible; SuboticaRSSResearch/1.0; news monitoring)','Accept':'text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.7'}
TIMEOUT=12
RSS_PATHS=['/feed/','/rss','/rss.xml','/feed.xml','/index.php?format=feed&type=rss']
DATE_RE=re.compile(r'(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)')
SESSION=requests.Session();SESSION.headers.update(HEAD)

def get(url):
 try:
  r=SESSION.get(url,timeout=TIMEOUT,allow_redirects=True)
  return r,None
 except requests.RequestException as e:return None,str(e)[:230]

def canon(u):
 p=urlsplit(u);return urlunsplit((p.scheme,p.netloc,p.path,'',''))

def dateval(s):
 if not s:return None
 s=str(s).strip()
 m=DATE_RE.search(s)
 if m:
  try:d=datetime(int(m[3]),int(m[2]),int(m[1]),tzinfo=timezone.utc)
  except ValueError:return None
 else:
  try:d=dateparser.parse(s,fuzzy=False)
  except (ValueError,TypeError,OverflowError):return None
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  d=d.astimezone(timezone.utc)
 return d if datetime(2018,1,1,tzinfo=timezone.utc)<=d<=NOW else None

def parse_feed(data,origin,keywords):
 try:root=fromstring(data)
 except Exception:return None
 tag=root.tag.lower()
 if not (tag.endswith('rss') or tag.endswith('feed') or tag.endswith('rdf')):return None
 out=[]
 for el in root.iter():
  if el.tag.split('}')[-1].lower() not in ('item','entry'):continue
  vals={};link=''
  for child in el:
   k=child.tag.split('}')[-1].lower()
   if k in ('title','pubdate','published','updated','date','description','summary') and k not in vals:vals[k]=''.join(child.itertext()).strip()
   if k=='link':link=child.attrib.get('href') or (child.text or '').strip()
  title=vals.get('title','');d=dateval(next((vals[k] for k in ('pubdate','published','date','updated') if vals.get(k)),''))
  if not title or not d or not link:continue
  u=urljoin(origin,link)
  if keywords and not any(x in (title+' '+u+' '+vals.get('description','')).lower() for x in keywords):continue
  out.append(dict(title=title[:240],link=canon(u),date=d,description=vals.get('description','')[:450]))
 return out

def html_articles(soup,origin,keywords):
 found={}
 # Only date tied to an article/card, never a date from a global page header.
 for block in soup.select('article, [class*="news-item"], [class*="post-item"], [class*="article-item"], [class*="vest-item"], [class*="news-card"], [class*="post-card"]')[:100]:
  a=block.select_one('h1 a[href],h2 a[href],h3 a[href],a[href]')
  if not a:continue
  title=a.get_text(' ',strip=True)
  if len(title)<12:continue
  url=urljoin(origin,a.get('href',''))
  if urlsplit(url).netloc.lower().removeprefix('www.')!=urlsplit(origin).netloc.lower().removeprefix('www.'):continue
  if keywords and not any(x in (title+' '+url).lower() for x in keywords):continue
  ds=[]
  for n in block.select('time[datetime], time, [class*="date"], [class*="datum"], [itemprop="datePublished"]')[:5]:
   ds.append(n.get('datetime') or n.get('content') or n.get_text(' ',strip=True))
  dt=next((d for s in ds if (d:=dateval(s))),None)
  if dt:found[canon(url)]=dict(title=title[:240],link=canon(url),date=dt,description='')
 return list(found.values())

def write_feed(src,items):
 path=f"feeds/final7-{src['id']}.xml"
 unique={x['link']:x for x in items};items=sorted(unique.values(),key=lambda x:x['date'],reverse=True)[:80]
 if not items:return None
 root=Element('rss',{'version':'2.0'});ch=SubElement(root,'channel')
 for k,v in [('title',src['label']),('link',src['urls'][0]),('description','Verified publication dates only; best-effort coverage'),('language','sr')]:SubElement(ch,k).text=v
 for item in items:
  e=SubElement(ch,'item')
  for k,v in [('title',item['title']),('link',item['link']),('guid',item['link']),('pubDate',format_datetime(item['date']))]:SubElement(e,k).text=v
  if item['description']:SubElement(e,'description').text=item['description']
 os.makedirs('feeds',exist_ok=True);ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
 return path

def process(src):
 report={'source':src['id'],'label':src['label'],'attempts':[],'discovered_feeds':[],'dated_items':0,'output':None,'status':'unresolved'}
 items=[];seen_feeds=set()
 for base in src['urls']:
  r,err=get(base)
  if err:report['attempts'].append({'url':base,'error':err});continue
  report['attempts'].append({'url':base,'http_status':r.status_code,'final_url':r.url})
  if r.status_code!=200:continue
  parsed=parse_feed(r.content,r.url,src['keywords'])
  if parsed is not None:items+=parsed;report['discovered_feeds'].append(r.url);continue
  soup=BeautifulSoup(r.content,'html.parser');items+=html_articles(soup,r.url,src['keywords'])
  candidates=[]
  for tag in soup.select('link[rel="alternate"][href]'):
   if 'rss' in tag.get('type','').lower() or 'atom' in tag.get('type','').lower():candidates.append(urljoin(r.url,tag['href']))
  for p in RSS_PATHS:candidates.append(urljoin(r.url,p))
  for feed_url in candidates[:9]:
   if feed_url in seen_feeds:continue
   seen_feeds.add(feed_url)
   fr,fe=get(feed_url)
   if fe or not fr or fr.status_code!=200:continue
   entries=parse_feed(fr.content,fr.url,src['keywords'])
   if entries is not None:report['discovered_feeds'].append(fr.url);items+=entries
  # First working homepage only; do not repeatedly probe variants of same website.
  break
 unique={i['link']:i for i in items}
 report['dated_items']=len(unique)
 report['sample']=[{'title':i['title'],'url':i['link'],'date':i['date'].isoformat()} for i in list(unique.values())[:4]]
 report['output']=write_feed(src,list(unique.values()))
 report['status']='feed_created' if report['output'] else ('blocked_or_unreachable' if not any(x.get('http_status')==200 for x in report['attempts']) else 'accessible_but_no_verified_dated_items')
 return report

def main():
 os.makedirs('audit-results',exist_ok=True)
 report={'generated_at':NOW.isoformat(),'note':'Only the seven user-approved additional sources are processed','sources':{}}
 for src in SOURCES:
  try:res=process(src)
  except Exception as e:res={'source':src['id'],'status':'exception','error':str(e)[:500]}
  report['sources'][src['id']]=res
  print(src['id'],res['status'],res.get('dated_items',0),flush=True)
 with open('audit-results/final7_rss_report.json','w',encoding='utf8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
