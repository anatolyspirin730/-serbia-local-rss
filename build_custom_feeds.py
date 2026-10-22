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
 'pogrebno': {'label':'Pogrebno Subotica','pages':['https://pogrebno.rs/vesti/'],'allow':[r'/vesti/']},
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
  result={'pages':[],'articles_found':0,'dated_articles':0,'output':None,'errors':[]};found={}
  for page in cfg['pages']:
   try:
    r=session.get(page,timeout=18);r.raise_for_status();soup=BeautifulSoup(r.content,'html.parser');links=candidates(soup,r.url,cfg)
    result['pages'].append({'url':page,'status':r.status_code,'candidate_links':len(links)})
    for title,url in links:found.setdefault(canonical(url),(title,url))
   except requests.RequestException as e:result['errors'].append({'url':page,'error':str(e)[:300]})
  result['articles_found']=len(found);items=[]
  for title,url in list(found.values())[:35]:
   try:
    r=session.get(url,timeout=12);r.raise_for_status();soup=BeautifulSoup(r.content,'html.parser');d=article_date(soup)
    if d and d<=datetime.now(timezone.utc):items.append({'title':title,'link':canonical(r.url),'date':d})
   except requests.RequestException:pass
  result['dated_articles']=len(items)
  # Preserve a previously working feed if the current run fails to find dated articles.
  if items:result['output']=write_feed(key,cfg,items)
  else:result['status']='needs_parser_refinement_or_no_dated_articles'
  report[key]=result;print(key,json.dumps(result,ensure_ascii=False))
 os.makedirs('audit-results',exist_ok=True)
 with open('audit-results/custom_feeds_report.json','w') as f:json.dump({'generated_at':datetime.now(timezone.utc).isoformat(),'sources':report},f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
