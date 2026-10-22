#!/usr/bin/env python3
"""Three source-specific RSS builders. Strict dates; never substitute unrelated news."""
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
URLS={'city-gazette':'https://subotica.ls.gov.rs/sluzbeni-list/?pismo=lat','cistoca':'https://www.cistoca-su.co.rs/lat/vesti/','electricity':'https://elektrodistribucija.rs/planirana-iskljucenja/planirana-ns'}
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
def gazette(soup,base):
 out={}
 # Only PDF links within the official gazette page. Do not ingest site-wide WordPress feed.
 for a in soup.select('a[href]'):
  href=urljoin(base,a['href']); label=a.get_text(' ',strip=True)
  if '.pdf' not in urlparse(href).path.lower():continue
  block=a.find_parent(['li','tr','p','div']) or a
  nearby=block.get_text(' ',strip=True)[:300]
  if not re.search(r'(služben|sluzben|службен|лист|list|broj|број|202[0-9])',label+' '+nearby,re.I):continue
  d=date_of(label+' '+nearby+' '+href)
  # Date from a year-only archive heading is NOT a publication date.
  if not d:continue
  add(out,'Službeni list Subotice — '+(label or nearby)[:140],href,d,nearby)
 return out
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
def electricity(soup,base):
 out={}
 # Only actual outage rows with date, time and Subotica area, not explanatory site text.
 for row in soup.select('tr, .table-row, [class*="iskljuc"]'):
  txt=row.get_text(' ',strip=True)
  if not re.search(r'subotic|суботиц|palić|палић|čantavir|чантавир',txt,re.I):continue
  d=date_of(txt)
  if not d or not re.search(r'\b\d{1,2}[:.]\d{2}\b',txt):continue
  anchor=row.select_one('a[href]');link=urljoin(base,anchor['href']) if anchor else base
  uid=hashlib.sha256(txt.encode()).hexdigest()[:14]
  add(out,'Плановое отключение электроэнергии — '+txt[:135],link+'#outage-'+uid,d,txt)
 return out
def write(name,items):
 if not items:return None
 root=Element('rss',version='2.0');ch=SubElement(root,'channel')
 for k,v in [('title','Subotica — '+name),('link',URLS[name]),('description','Verified source-specific feed')]:SubElement(ch,k).text=v
 for it in sorted(items.values(),key=lambda x:x['date'],reverse=True)[:80]:
  node=SubElement(ch,'item')
  for k,v in [('title',it['title']),('link',it['link']),('guid',it['link']),('pubDate',format_datetime(it['date'])),('description',it['description'])]:SubElement(node,k).text=v
 target=BASE/('special-'+name+'.xml');ElementTree(root).write(target,encoding='utf-8',xml_declaration=True);return str(target)
for name,url in URLS.items():
 info={'url':url,'status':'unknown','count':0,'samples':[]}
 try:
  r=fetch(url);soup=BeautifulSoup(r.content,'html.parser')
  info['http_status']=r.status_code;info['page_title']=soup.title.get_text(' ',strip=True)[:120] if soup.title else ''
  info['pdf_links']=[urljoin(r.url,a['href']) for a in soup.select('a[href]') if '.pdf' in a['href'].lower()][:15]
  info['tables']=len(soup.select('table'));info['date_matches']=DATE.findall(soup.get_text(' ',strip=True))[:15]
  info['sample_links']=[{'text':a.get_text(' ',strip=True)[:90],'url':urljoin(r.url,a['href'])} for a in soup.select('a[href]') if len(a.get_text(' ',strip=True))>10][:20]
  items={'city-gazette':gazette,'cistoca':cistoca,'electricity':electricity}[name](soup,r.url)
  info['count']=len(items);info['output']=write(name,items);info['status']='feed_created' if items else 'needs_targeted_revision'
  info['samples']=[{'title':v['title'],'url':v['link'],'date':v['date'].isoformat()} for v in list(items.values())[:5]]
 except Exception as e:info['status']='fetch_error';info['error']=str(e)[:400]
 REPORT[name]=info;print(name,info['status'],info['count'])
(AUD/'special3_report.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf8')
