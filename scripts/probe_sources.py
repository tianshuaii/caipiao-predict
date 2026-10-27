"""Read-only source discovery. Does not send notifications or read secrets."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

URLS = {
    'zhcw-js': 'https://www.zhcw.com/static/unjs/kj-wq.js?2026',
    'zhcw-common': 'https://www.zhcw.com/static/js/kjsj.min.js',
    'cwl-nav': 'https://www.cwl.gov.cn/gywm/',
    'sh-old-ssl': 'https://appsh.swlc.net.cn/shfcoc_ldatacenter/aword/execQueryAllAnalysis.ctl?lottcode=01&num=9999&ttype=1',
}
def fetch(item):
    name,url=item
    p=Path('/tmp/lottery-'+name+'.txt')
    r=subprocess.run(['curl','-L','--max-time','30','-sS',url,'-o',str(p)],capture_output=True,text=True)
    return name,r.returncode,p.stat().st_size if p.exists() else 0
if __name__=='__main__':
    for row in ThreadPoolExecutor(5).map(fetch, URLS.items()): print(row)
