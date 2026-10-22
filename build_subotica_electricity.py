#!/usr/bin/env python3
"""RSS from EDS Novi Sad daily outage tables, restricted to municipality Subotica."""
import hashlib, json, os, re, sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

BASE='https://elektrodistribucija.rs/planirana-iskljucenja-srbija/NoviSad_Dan_{}_Iskljucenja.htm'
OUT=Path('feeds/special-electricity.xml')
REPORT=Path('electricity_diagnostic.json')
DATE_RE=re.compile(r'(?<!\d)(\d{1,2})\.(\d{1,2})\.(20\d{2})\.')
TIME_RE=re.compile(r'\b\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\b')

def clean(s): return ' '.join(s.split())
def norm(s):
    return clean(s).casefold().translate(str.maketrans({'с':'s','у':'u','б':'b','о':'o','т':'t','и':'i','ц':'c','а':'a'}))
def is_subotica(s):
    return clean(s).casefold() in ('суботица','subotica')

def fetch(day,session):
    url=BASE.format(day)
    r=session.get(url,timeout=35,headers={'User-Agent':'Mozilla/5.0 (compatible; SuboticaLocalRSS/1.0)'})
    r.raise_for_status()
    r.encoding=r.apparent_encoding if r.apparent_encoding and r.apparent_encoding.lower() not in ('windows-1252','iso-8859-1') else (r.encoding or 'utf-8')
    soup=BeautifulSoup(r.content,'html.parser')
    # BS4 decodes from original bytes, independently of requests' guessed encoding.
    title=clean(soup.get_text(' ',strip=True)[:700])
    m=DATE_RE.search(title)
    if not m: raise ValueError('Date absent in page heading; refusing to invent publication date')
    day_date=datetime(int(m[3]),int(m[2]),int(m[1]),tzinfo=timezone.utc)
    items=[]; candidates=[]
    for tr in soup.select('tr'):
        cells=tr.find_all(['td','th'],recursive=False)
        if len(cells)<4: continue
        vals=[clean(c.get_text(' ',strip=True)) for c in cells]
        candidates.append(vals[:4])
        branch,municipality,hours,streets=vals[:4]
        # Municipality is column TWO. Branch Subotica alone also includes Kanjiža.
        if not is_subotica(municipality): continue
        if not TIME_RE.search(hours) or not streets: continue
        unique=f'{day_date.date()}|{municipality}|{hours}|{streets}'
        guid='eds-subotica-'+hashlib.sha256(unique.encode()).hexdigest()[:24]
        locality=streets.split(':',1)[0][:70] if ':' in streets else 'Суботица'
        items.append({'guid':guid,'title':f'Отключение электричества — {locality}, {day_date:%d.%m.%Y}, {hours}',
                      'description':f'Дата: {day_date:%d.%m.%Y}. Время: {hours}. Населённый пункт и адреса: {streets}',
                      'date':day_date,'link':url,'municipality':municipality})
    return {'url':url,'status':r.status_code,'date':day_date.date().isoformat(),
            'total_table_rows':len(candidates),'subotica_rows':len(items),'sample_rows':candidates[:4]},items

def write_rss(items):
    ET.register_namespace('atom','http://www.w3.org/2005/Atom')
    root=ET.Element('rss',version='2.0'); ch=ET.SubElement(root,'channel')
    for k,v in [('title','Суботица — плановые отключения электричества (ЕДС)'),('link',BASE.format(0)),
                ('description','Официальные плановые отключения: только општина Суботица (включая Палич и населённые пункты муниципалитета).'),
                ('language','ru-RU')]: ET.SubElement(ch,k).text=v
    ET.SubElement(ch,'lastBuildDate').text=format_datetime(datetime.now(timezone.utc))
    for row in sorted(items,key=lambda i:(i['date'],i['guid']),reverse=True):
        el=ET.SubElement(ch,'item')
        for k,v in [('title',row['title']),('link',row['link']),('guid',row['guid']),('description',row['description']),('pubDate',format_datetime(row['date']))]:
            node=ET.SubElement(el,k);node.text=v
            if k=='guid':node.set('isPermaLink','false')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    ET.indent(root,space='  ')
    ET.ElementTree(root).write(OUT,encoding='utf-8',xml_declaration=True)

def main():
    session=requests.Session(); report={'source':'EDS Novi Sad planned outages','only_municipality':'Суботица','pages':[],'errors':[]}
    found={}
    for day in (0,1,2):
        try:
            page,items=fetch(day,session);report['pages'].append(page)
            for item in items: found[item['guid']]=item
            print('day',day,'date',page['date'],'rows',page['total_table_rows'],'subotica',len(items))
        except Exception as exc:
            report['errors'].append({'day':day,'error':str(exc)});print('day',day,'ERROR',exc)
    report['items']=len(found)
    # Preserve an existing good RSS if today's table has no outages or site is temporarily broken.
    if found:
        write_rss(list(found.values()));report['status']='feed_created';report['output']=str(OUT)
    else:
        report['status']='no_verified_subotica_outages';report['output']=None
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RESULT',report['status'],report['items'])
    if not report['pages']: sys.exit(1)

if __name__=='__main__':main()
