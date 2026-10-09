"""Export only attendance summaries; never publish raw workflow logs."""
import concurrent.futures
import datetime
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import urllib.error

BASE = 'https://api.github.com/repos/dixuan-pixel/attendance-bot'
TOKEN = os.environ['GITHUB_TOKEN']
class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlparse(newurl).netloc != urllib.parse.urlparse(req.full_url).netloc:
            redirected.remove_header('Authorization')
        return redirected
OPENER = urllib.request.build_opener(SafeRedirect)
def get(path, raw=False):
    req = urllib.request.Request(BASE+path, headers={'Authorization': 'Bearer '+TOKEN, 'Accept':'application/vnd.github+json','User-Agent':'Haoda-Attendance'})
    for attempt in range(3):
        try:
            with OPENER.open(req, timeout=30) as response:
                data = response.read().decode()
            return data if raw else json.loads(data)
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2: raise
            time.sleep(2)
def parse(log):
    lines = [re.sub(r'^\d{4}-\d{2}-\d{2}T\S+\s+', '', l).strip() for l in log.splitlines()]
    starts=[i for i,l in enumerate(lines) if l=='【考勤通报】']
    if not starts:return None
    groups=[[],[],[],[]]; found=set(); current=-1
    for line in lines[starts[-1]+1:]:
        m=re.match(r'^([1-4])\.\s*.+人员[：:]\s*$',line)
        if m:
            current=int(m[1])-1;found.add(current);continue
        if not line:continue
        if current<0 or re.match(r'^(✅|❌|⚠|##|Post job|Cleaning|网页快照已生成)',line):break
        if line!='无':groups[current].extend(n.strip() for n in line.split('、') if n.strip())
    if len(found)!=4:return None
    total=re.search(r'找到 (\d+) 名成员',log)
    return {'groups':[list(dict.fromkeys(g)) for g in groups],'total':int(total[1]) if total else None}
def export_run(run):
    item={k:run[k] for k in ('id','created_at','status','conclusion')}
    item['report']=None
    item['source']='web_only' if run['name']=='考勤网页快照' else 'group_report'
    if run['status']!='completed':
        item['reason']='任务正在运行';return item
    jobs=get(f"/actions/runs/{run['id']}/jobs?per_page=100")['jobs']
    for job in jobs:
        if job['name'] not in ('attendance','snapshot'):continue
        try:
            log=get(f"/actions/jobs/{job['id']}/logs?nonce={time.time_ns()}",True)
        except urllib.error.HTTPError as e:
            if e.code in (404,410):
                item['reason']='历史日志已过期';return item
            raise
        item['report']=parse(log)
        metas=re.findall(r'SNAPSHOT_META=(\{[^\n]+\})',log)
        if metas:
            meta=json.loads(metas[-1])
            item['collection_started']=meta.get('collection_started')
            item['collected_at']=meta.get('collected_at')
        if item['report']:break
    if not item['report']:item['reason']='本次未生成通报，可能因休息日跳过或取数失败'
    return item
if __name__=='__main__':
    runs=get('/actions/workflows/schedule.yml/runs?per_page=100')['workflow_runs']
    runs+=get('/actions/workflows/snapshot.yml/runs?per_page=100')['workflow_runs']
    runs=sorted(runs,key=lambda r:r['created_at'],reverse=True)[:100]
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        records=list(pool.map(export_run,runs))
    Path('web').mkdir(exist_ok=True)
    Path('web/data.json').write_text(json.dumps({'updated':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runs':records},ensure_ascii=False),encoding='utf8')
    print(f'Exported {len(records)} records, {sum(bool(r["report"]) for r in records)} reports')
