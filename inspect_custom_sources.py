#!/usr/bin/env python3
"""Read-only HTML diagnostics for Subotica sources; does not alter feeds."""
import json, re, os, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit
from datetime import datetime, timezone
SITES = {
 'vodovod': ['https://vodovodsu.rs/informacije/8-servisne-informacije','https://vodovodsu.rs/informacije/7-vazne-informacije'],
 'palic-ludas': ['https://palic-ludas.rs/index/pagelist/id_page_node/26/lg/cp'],
 'pogrebno': ['https://pogrebno.rs/vesti/', 'https://pogrebno.rs/'],
 'rtv-subotica': ['https://www.rtv.rs/sr_lat/vojvodina/', 'https://www.rtv.rs/sr_lat/', 'https://www.rtv.rs/'],
}
HEADERS={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36','Accept-Language':'sr-RS,sr;q=0.9,en;q=0.7'}
def tidy(x,n=300):return ' '.join((x or '').split())[:n]
def probe(url):
 out={'requested_url':url}
 try:
  r=requests.get(url,headers=HEADERS,timeout=20);out.update({'status':r.status_code,'final_url':r.url,'content_type':r.headers.get('content-type','')})
  if r.status_code>=400:return out
  soup=BeautifulSoup(r.content,'html.parser');out['page_title']=tidy(soup.title.get_text(' ',strip=True) if soup.title else '')
  out['date_samples']=[{'tag':t.name,'class':t.get('class'),'datetime':t.get('datetime'),'content':t.get('content'),'text':tidy(t.get_text(' ',strip=True),160)} for t in soup.select('time, [class*=date], [class*=datum], [itemprop*=date], meta[property*=time], meta[name*=date]')[:30]]
  out['jsonld_samples']=[tidy(t.string,600) for t in soup.select('script[type="application/ld+json"]')[:5]]
  links=[];seen=set()
  for a in soup.select('a[href]'):
   u=urljoin(r.url,a['href']);t=tidy(a.get_text(' ',strip=True),150)
   if urlsplit(u).netloc != urlsplit(r.url).netloc or u in seen or not t:continue
   seen.add(u)
   links.append({'text':t,'url':u,'parent_class':tidy(' '.join(a.parent.get('class',[])) if a.parent else '',100)})
  out['links_total']=len(links);out['links_sample']=links[:110]
 except Exception as e:out['error']=str(e)[:500]
 return out

def main():
 data={'generated_at':datetime.now(timezone.utc).isoformat(),'sites':{}}
 for name,urls in SITES.items():
  data['sites'][name]=[probe(u) for u in urls]
  print(name,[(x.get('status'),x.get('links_total'),x.get('error')) for x in data['sites'][name]])
 os.makedirs('audit-results',exist_ok=True)
 with open('audit-results/custom_sources_html_diagnostic.json','w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
