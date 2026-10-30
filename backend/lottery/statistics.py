"""Frozen-family exploratory diagnostics calibrated on full lottery draws."""
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
import tempfile
import numpy as np
from scipy.stats import hypergeom
from .domain import GAMES,canonical_issue,rule_version,validate_ticket

VERSION='randomness-center-v1'
SEED=20261028
FAMILIES=('frequency','sum','odd','adjacent','lag1','runs','drift')


def sum_pmf(maximum,count):
    dp=np.zeros((count+1,maximum*count+1),dtype=np.int64);dp[0,0]=1
    for value in range(1,maximum+1):
        for k in range(count,0,-1): dp[k,value:]+=dp[k-1,:-value]
    return dp[count]/math.comb(maximum,count)


def adjacent_pmf(maximum,count):
    return np.array([math.comb(count-1,count-a-1)*math.comb(maximum-count+1,count-a)/math.comb(maximum,count) for a in range(count)])


def _statistics(numbers,maximum,count,pmfs,edges):
    n=len(numbers);sums=numbers.sum(axis=1);mu=count*(maximum+1)/2
    counts=np.bincount(numbers.ravel(),minlength=maximum+1)[1:]
    result=[float(np.sum((counts-n*count/maximum)**2/(n*count/maximum)))]
    values=(sums,(numbers%2).sum(axis=1),(np.diff(np.sort(numbers,axis=1),axis=1)==1).sum(axis=1))
    for value,pmf in zip(values,pmfs):
        obs=np.bincount(value,minlength=len(pmf));positive=pmf>0
        result.append(float(np.sum((obs[positive]-n*pmf[positive])**2/(n*pmf[positive]))))
    variance=count*(maximum-count)/(maximum-1)*(maximum**2-1)/12
    result.append(float(abs(np.mean(((sums[:-1]-mu)*(sums[1:]-mu))[edges]))/variance) if edges.any() else 0.)
    high=sums>=mu;p=float(pmfs[0][math.ceil(mu):].sum())
    transitions=int(np.count_nonzero((high[:-1]!=high[1:])&edges))
    result.append(abs(transitions-2*int(edges.sum())*p*(1-p)))
    midpoint=n//2
    result.append(float(abs(sums[:midpoint].mean()-sums[midpoint:].mean())))
    return np.asarray(result)


def _canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def analyze(dataset,simulations=999,seed=SEED):
    if type(simulations) is not int or not 99<=simulations<=4999: raise ValueError('Simulations must be 99–4999')
    if type(seed) is not int or not 0<=seed<2**32: raise ValueError('Invalid seed')
    games=dataset.get('games')
    if not isinstance(games,dict) or not games or any(game not in GAMES for game in games): raise ValueError('Invalid games')
    if sum(len(rows) for rows in games.values())>10000: raise ValueError('At most 10000 draws')
    tests=[];skipped=[];groups=[];rng=np.random.default_rng(seed)
    for game,rows in sorted(games.items()):
        previous=None;versions={}
        for row in rows:
            issue=canonical_issue(row['issue']);day=date.fromisoformat(row.get('draw_date') or row['date'])
            if issue!=row['issue'] or previous and (issue<=previous[0] or day<previous[1]): raise ValueError('Expected ordered unique canonical draws')
            if row.get('conflict'): raise ValueError('Conflicted draw')
            for zone in ('front','back'):
                if any(type(v) is not int for v in row[zone]):raise ValueError('Integer numbers required')
            validate_ticket(game,row['front'],row['back'])
            version=rule_version(game,issue)
            if row.get('rule_version',version)!=version: raise ValueError('Rule version mismatch')
            versions.setdefault(version,[]).append(row);previous=(issue,day)
        for version,items in versions.items():
            n=len(items);identity={'game':game,'rule_version':version,'periods':n,'from_issue':items[0]['issue'],'to_issue':items[-1]['issue']}
            if n<30:
                skipped.append({**identity,'reason':'fewer_than_30_draws'});continue
            edges=np.array([a['issue'][:4]==b['issue'][:4] and int(b['issue'])==int(a['issue'])+1 for a,b in zip(items,items[1:])])
            groups.append({**identity,'serial_edges':int(edges.sum()),'serial_breaks':int((~edges).sum())})
            for zone in ('front','back'):
                maximum,count=GAMES[game][zone]
                pmfs=(sum_pmf(maximum,count),hypergeom.pmf(np.arange(count+1),maximum,(maximum+1)//2,count),adjacent_pmf(maximum,count))
                observed=_statistics(np.array([r[zone] for r in items]),maximum,count,pmfs,edges)
                exceed=np.zeros(len(FAMILIES),dtype=int)
                for _ in range(simulations):
                    # Random ranks choose a uniform k-subset independently for each draw.
                    sample=np.argsort(rng.random((n,maximum)),axis=1)[:,:count]+1
                    exceed+=_statistics(sample,maximum,count,pmfs,edges)>=observed-1e-12
                for i,family in enumerate(FAMILIES):
                    tests.append({**identity,'zone':zone,'family':family,'statistic':float(observed[i]),
                                  'p':float((exceed[i]+1)/(simulations+1)),
                                  'serial_edges':int(edges.sum()) if family in ('lag1','runs') else None,
                                  'informative':bool(edges.any()) if family in ('lag1','runs') else not(family=='adjacent' and count==1)})
    previous=0.
    for rank,index in enumerate(sorted(range(len(tests)),key=lambda i:tests[i]['p'])):
        previous=max(previous,min(1.,tests[index]['p']*(len(tests)-rank)));tests[index]['holm_p']=previous
    return {'version':VERSION,'seed':seed,'simulations':simulations,'minimum_p':1/(simulations+1),
            'family':list(FAMILIES),'multiple_testing':'Holm across all tests in this report; alpha=0.05',
            'post_hoc':True,'data_mode':'supplied-frozen-snapshot','dataset_sha256':hashlib.sha256(_canonical(dataset)).hexdigest(),
            'null':'Independent uniform draws; without replacement within each zone; zones simulated separately.',
            'groups':groups,'skipped':skipped,'total_tests':len(tests),'tests':tests,
            'significant':[t for t in tests if t['holm_p']<.05],
            'note':'固定检验族，完整无放回序列蒙特卡洛校准；p值采用加一法。规则版本分组，序列检验不跨缺期/年界。单报告Holm不校正跨窗口/跨报告挑选，所有分析标记探索性；不证明公平或可预测，不触发晋升。'}


def save_report(dataset,report,directory):
    if hashlib.sha256(_canonical(dataset)).hexdigest()!=report['dataset_sha256']: raise ValueError('Snapshot hash mismatch')
    raw=_canonical({'snapshot':dataset,'report':report});key=hashlib.sha256(raw).hexdigest()
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory,delete=False) as file:
        temporary=Path(file.name);file.write(raw)
    temporary.replace(directory/(key+'.json'))
    return key


def read_report(key,directory):
    if not re.fullmatch(r'[0-9a-f]{64}',key): raise ValueError('Invalid report id')
    raw=(Path(directory)/(key+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=key:raise ValueError('Report integrity failure')
    value=json.loads(raw)
    if hashlib.sha256(_canonical(value['snapshot'])).hexdigest()!=value['report']['dataset_sha256']:raise ValueError('Snapshot integrity failure')
    return value


def run_file(path,simulations=999,seed=SEED,directory=None):
    import csv
    from .config import RUNTIME
    path=Path(path)
    for name in ('analysis.json','tests.csv'):
        output=path.parent/name
        if output.resolve()==path.resolve() or output.exists() and output.samefile(path):
            raise ValueError('Input snapshot conflicts with output file')
    raw=path.read_bytes();dataset=json.loads(raw)
    report=analyze(dataset,simulations,seed)
    report['source_sha256']=hashlib.sha256(raw).hexdigest()
    key=save_report(dataset,report,directory if directory is not None else RUNTIME/'statistics')
    (path.parent/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (path.parent/'tests.csv').open('w',encoding='utf-8',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['game','zone','rule_version','family','p','holm_p','statistic'],extrasaction='ignore')
        writer.writeheader();writer.writerows(report['tests'])
    return key


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Frozen-snapshot exploratory statistics')
    parser.add_argument('dataset');parser.add_argument('--simulations',type=int,default=999)
    parser.add_argument('--seed',type=int,default=SEED)
    args=parser.parse_args()
    print(json.dumps({'report_id':run_file(args.dataset,args.simulations,args.seed)},ensure_ascii=False))
