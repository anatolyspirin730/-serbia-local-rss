#!/usr/bin/env python3
"""Read-only audit of municipal/local sources. No insecure TLS bypass or fabricated RSS."""
import json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

TARGETS = {
 'subotica-city':'https://www.subotica.rs/',
 'vodovodsu':'https://vodovodsu.rs/',
 'sutrans':'https://sutrans.rs/',
 'cistoca-su':'https://cistoca-su.rs/',
 'suparking':'https://suparking.rs/',
 'deponija':'https://deponija.rs/',
 'palic-ludas':'https://palic-ludas.rs/',
 'pogrebno':'https://pogrebno.rs/',
 'subotica-info':'https://www.subotica.info/',
 'maglocistac':'https://www.maglocistac.rs/',
 'magyarszo':'https://www.magyarszo.rs/',
 'rtv':'https://www.rtv.rs/',
 'stadion':'https://jkp-stadion.rs/',
 'supijace':'https://supijace.co.rs/',
}
KEYWORDS = re.compile(r'vest|novost|aktuel|obavešt|obavest|saopšt|saopst|isklju|radov|kvar|inform|hír|szabadka|subotic|palić|palic|rss|feed|sitemap',re.I)
UA={'User-Agent':'Mozilla/5.0 (compatible; SuboticaTodaySourceAudit/1.0; +https://github.com/anatolyspirin730/-serbia-local-rss)', 'Accept':'text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8'}
S=requests.Session();S.headers.update(UA)

def variants(url):
 p=urlparse(url); host=p.hostname or ''; bare=host[4:] if host.startswith('www.') else host
 return list(dict.fromkeys([url, 'https://'+bare+'/', 'https://www.'+bare+'/', 'http://'+bare+'/', 'http://www.'+bare+'/']))

def check(url):
 try:
  r=S.get(url,timeout=(5,9),allow_redirects=True)
  content=r.content[:250000]
  typ=r.headers.get('content-type','')
  is_feed=bool(re.search(br'<(?:rss\b|feed\b|rdf:RDF\b)',content[:1200],re.I))
  result={'url':url,'status':r.status_code,'final_url':r.url,'content_type':typ,'feed_xml':is_feed}
  if r.ok and 'html' in typ.lower():
   soup=BeautifulSoup(content,'html.parser')
   result['title']=soup.title.get_text(' ',strip=True)[:150] if soup.title else ''
   found=[]
   for a in soup.select('a[href]'):
    label=a.get_text(' ',strip=True)[:90]; href=urljoin(r.url,a['href'])
    if KEYWORDS.search(label+' '+href) and urlparse(href).hostname == urlparse(r.url).hostname:
     found.append({'title':label,'url':href})
   result['candidate_sections']=list({v['url']:v for v in found}.values())[:35]
  return result
 except requests.exceptions.SSLError as e: return {'url':url,'error_type':'ssl','error':str(e)[:220]}
 except requests.exceptions.RequestException as e: return {'url':url,'error_type':type(e).__name__,'error':str(e)[:220]}

def main():
 report={'checked_at':datetime.now(timezone.utc).isoformat(),'purpose':'Identify reachable official sections and feeds; not a feed-creation claim','sources':{}}
 for name,url in TARGETS.items():
  checks=[]
  for v in variants(url):
   checks.append(check(v))
  best=next((x for x in checks if x.get('status')==200 and x.get('candidate_sections')),None)
  base=best['final_url'] if best else next((x['final_url'] for x in checks if x.get('status')==200),url)
  p=urlparse(base);root=f'{p.scheme}://{p.netloc}'
  probes=[]
  for path in ('/feed/','/rss.xml','/rss/','/feed.xml','/sitemap.xml','/robots.txt'):
   probes.append(check(root+path))
  report['sources'][name]={'homepage_attempts':checks,'discovery_probes':probes}
  print(f"{name}: homepage={[(x.get('status'),x.get('error_type')) for x in checks]} feeds={[(x['url'],x.get('status'),x.get('feed_xml')) for x in probes if x.get('feed_xml') or x.get('status')==200]}",flush=True)
  time.sleep(.1)
 out=Path('audit-results');out.mkdir(exist_ok=True)
 (out/'city_sources_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved audit-results/city_sources_report.json')

if __name__=='__main__':main()
