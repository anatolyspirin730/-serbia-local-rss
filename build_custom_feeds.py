#!/usr/bin/env python3
"""Best-effort source-specific RSS extraction. Never invent publication dates."""
import json,re,os,html,hashlib
from datetime import datetime,timezone
from email.utils import format_datetime
from urllib.parse import urljoin,urlsplit,urlunsplit
from xml.etree.ElementTree import Element,SubElement,ElementTree
import requests
from bs4 import BeautifulSoup

SOURCES={
 'vodovod': {'label':'Vodovod Subotica','pages':['https://vodovodsu.rs/informacije/8-servisne-informacije','https://vodovodsu.rs/informacije/7-vazne-informacije','https://vodovodsu.rs/informacije/2-informacije'],'allow':[r'/8-servisne-informacije/',r'/7-vazne-informacije/',r'/2-informacije/']},
 'palic-ludas': {'label':'Palić-Ludaš','pages':['https://palic-ludas.rs/index/pagelist/id_page_node/26/lg/cp'],'allow':[r'/index/page/id/']},
 'pogrebno': {'label':'Pogrebno Subotica','pages':['https://pogrebno.rs/vesti/'],'allow':[r'/vesti/',r'^/[^/]+/$']},
 'magyarszo-szabadka': {'label':'Magyar Szó — Szabadka','pages':['https://www.magyarszo.rs/vajdasag/szabadka/'],'allow':[r'/vajdasag/',r'/kozelet/']},
 'rtv-subotica': {'label':'RTV Vojvodina — Subotica','pages':['https://www.rtv.rs/sr_lat/vojvodina/backa/'],'allow':[r'/vojvodina/backa/']},
}
UA={'User-Agent':'Mozilla/5.0 (compatible; SuboticaTodayRSS/1.0; local news monitoring)','Accept-Language':'sr,en;q=0.8'}
DATE_RE=re.compile(r'(?:20\d{2}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]20\d{2})')
def parse_date(s):
 if not s:return None
 s=s.strip()
 try:
  from dateutil import parser
  d=parser.parse(s,dayfirst=bool(re.match(r'^\d{1,2}[./-]',s)),fuzzy=False)
  if d.tzinfo is None:d=d.replace(tzinfo=timezone.utc)
  return d.astimezone(timezone.utc)
 except (ValueError,TypeError,OverflowError):return None

def canonical(u):
 s=urlsplit(u);return urlunsplit((s.scheme,s.netloc,s.path.rstrip('/') or '/', '', ''))
def candidates(soup,base,cfg):
 out=[];seen=set()
 for a in soup.select('article a[href], main a[href], .content a[href], .item a[href], .news a[href], a[href]'):
  href=a.get('href','');u=urljoin(base,href); parts=urlsplit(u)
  if parts.netloc.lower().removeprefix('www.')!=urlsplit(base).netloc.lower().removeprefix('www.'):continue
  if not any(re.search(p,parts.path,re.I) for p in cfg['allow']):continue
  if canonical(u)==canonical(base) or canonical(u) in seen:continue
  title=' '.join(a.get_text(' ',strip=True).split())
  if len(title)<18 or len(title)>240:continue
  seen.add(canonical(u));out.append((title,u))
 return out[:70]

def article_date(soup):
 for tag in soup.select('meta[property="article:published_time"],meta[name="date"],meta[itemprop="datePublished"],time[datetime],meta[property="og:updated_time"]'):
  raw=tag.get('content') or tag.get('datetime')
  d=parse_date(raw)
  if d:return d
 for node in soup.select('article time, .date, .datum, .published, time')[:8]:
  raw=node.get('datetime') or node.get_text(' ',strip=True)
  m=DATE_RE.search(raw)
  if m:
   d=parse_date(m.group())
   if d:return d
 return None

# Source-specific listing extraction: the listing itself displays dates, while
# article pages may omit machine-readable publication metadata.
MONTHS={'јан':1,'феб':2,'мар':3,'апр':4,'мај':5,'јун':6,'јул':7,'авг':8,'сеп':9,'окт':10,'нов':11,'дец':12}
def listing_date(text):
 text=' '.join(text.split()).lower()
 m=re.search(r'(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)',text)
 if m:
  try:return datetime(int(m[3]),int(m[2]),int(m[1]),tzinfo=timezone.utc)
  except ValueError:return None
 m=re.search(r'(јан|феб|мар|апр|мај|јун|јул|авг|сеп|окт|нов|дец)[а-я]*\s+(20\d{2})\s+(\d{1,2})',text)
 if m:
  try:return datetime(int(m[2]),MONTHS[m[1]],int(m[3]),tzinfo=timezone.utc)
  except ValueError:return None
 return None

def listing_items(soup,base,key):
 out={}
 if key=='vodovod':
  for a in soup.select('a[href]'):
   u=urljoin(base,a.get('href',''));path=urlsplit(u).path
   if not re.match(r'^/(?:7-vazne-informacije|8-servisne-informacije|2-informacije)/[^/]+',path):continue
   card=a.find_parent(class_=re.compile(r'space-y-3|relative pb-10')) or a.parent
   d=listing_date(a.get_text(' ',strip=True)) or listing_date(card.get_text(' ',strip=True))
   title=(card.find(['h2','h3','h4']) or card).get_text(' ',strip=True)
   title=re.sub(r'^(?:јан|феб|мар|апр|мај|јун|јул|авг|сеп|окт|нов|дец)[а-я]*\s+20\d{2}\s+\d{1,2}\s*','',title,flags=re.I).strip()
   if d and len(title)>=12:out[canonical(u)]={'title':title[:220],'link':canonical(u),'date':d}
 if key=='pogrebno':
  for a in soup.select('a[href]'):
   u=urljoin(base,a.get('href',''));path=urlsplit(u).path
   if urlsplit(u).netloc.lower().removeprefix('www.')!='pogrebno.rs':continue
   if not re.match(r'^/[^/]+/?$',path) or path in ('/','/vesti/'):continue
   card=a.find_parent('article') or a.find_parent(class_=re.compile('post|news|entry',re.I))
   if not card:continue
   d=listing_date(card.get_text(' ',strip=True))
   h=card.find(['h2','h3','h4'])
   title=h.get_text(' ',strip=True) if h else ''
   if d and len(title)>=12:out[canonical(u)]={'title':title[:220],'link':canonical(u),'date':d}
 return out

def write_feed(key,cfg,items):
 root=Element('rss',{'version':'2.0'});ch=SubElement(root,'channel')
 for k,v in [('title',cfg['label']),('link',cfg['pages'][0]),('description','Source-specific RSS, verified dates only'),('language','sr')]:SubElement(ch,k).text=v
 for x in sorted(items,key=lambda z:z['date'],reverse=True)[:60]:
  node=SubElement(ch,'item');SubElement(node,'title').text=x['title'];SubElement(node,'link').text=x['link'];SubElement(node,'guid',{'isPermaLink':'true'}).text=x['link'];SubElement(node,'pubDate').text=format_datetime(x['date'])
 path=f'feeds/custom-{key}.xml';os.makedirs('feeds',exist_ok=True)
 ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
 return path

def main():
 session=requests.Session();session.headers.update(UA);report={}
 for key,cfg in SOURCES.items():
  result={'pages':[],'articles_found':0,'dated_articles':0,'listing_dated':0,'output':None,'errors':[]};found={};listing_found={}
  for page in cfg['pages']:
   try:
    r=session.get(page,timeout=18);r.raise_for_status();soup=BeautifulSoup(r.content,'html.parser');links=candidates(soup,r.url,cfg);listing_found.update(listing_items(soup,r.url,key))
    result['pages'].append({'url':page,'status':r.status_code,'candidate_links':len(links)})
    for title,url in links:found.setdefault(canonical(url),(title,url))
   except requests.RequestException as e:result['errors'].append({'url':page,'error':str(e)[:300]})
  result['articles_found']=len(found);result['listing_dated']=len(listing_found);items=list(listing_found.values());dated_urls=set(listing_found)
  for title,url in list(found.values())[:35]:
   if canonical(url) in dated_urls:continue
   try:
    r=session.get(url,timeout=12);r.raise_for_status();soup=BeautifulSoup(r.content,'html.parser');d=article_date(soup)
    if d and d<=datetime.now(timezone.utc):items.append({'title':title,'link':canonical(r.url),'date':d})
   except requests.RequestException:pass
  items=[x for x in items if x['date']<=datetime.now(timezone.utc)];result['dated_articles']=len(items)
  # Preserve a previously working feed if the current run fails to find dated articles.
  if items:result['output']=write_feed(key,cfg,items)
  else:result['status']='needs_parser_refinement_or_no_dated_articles'
  report[key]=result;print(key,json.dumps(result,ensure_ascii=False))
 os.makedirs('audit-results',exist_ok=True)
 with open('audit-results/custom_feeds_report.json','w') as f:json.dump({'generated_at':datetime.now(timezone.utc).isoformat(),'sources':report},f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
