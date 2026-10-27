"""Read-only reproducible audit of a frozen draw snapshot; no application writes."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.stats import binomtest, chi2_contingency, hypergeom

SPECS={'dlt':{'front':(35,5),'back':(12,2)},'ssq':{'front':(33,6),'back':(16,1)}}
SEED=20261026

def holm(values):
    order=np.argsort(values)
    out=np.empty(len(values));previous=0.
    for rank,index in enumerate(order):
        previous=max(previous,min(1.,values[index]*(len(values)-rank)))
        out[index]=previous
    return out


def sum_pmf(maximum,count):
    dp=np.zeros((count+1,maximum*count+1),dtype=np.int64);dp[0,0]=1
    for value in range(1,maximum+1):
        for k in range(count,0,-1): dp[k,value:]+=dp[k-1,:-value]
    return dp[count]/math.comb(maximum,count)


def adjacent_pmf(maximum,count):
    return np.array([math.comb(count-1,count-a-1)*math.comb(maximum-count+1,count-a)/math.comb(maximum,count) for a in range(count)])


def goodness(values,probabilities,rng,simulations):
    n=len(values);p=np.asarray(probabilities,dtype=float)
    observed=np.bincount(values,minlength=len(p))
    assert len(observed)==len(p) and not np.any(observed[p==0]),'Impossible observation'
    groups=[];indices=[];mass=0.
    for i in np.flatnonzero(p>0):
        indices.append(i);mass+=p[i]
        if mass*n>=5: groups.append(indices);indices=[];mass=0.
    if indices:
        if groups:groups[-1]+=indices
        else:groups=[indices]
    if len(groups)<2:return None
    probs=np.array([p[ix].sum() for ix in groups]);probs/=probs.sum()
    obs=np.array([observed[ix].sum() for ix in groups]);expected=n*probs
    stat=float(np.sum((obs-expected)**2/expected))
    exceed=0
    for start in range(0,simulations,10000):
        simulated=rng.multinomial(n,probs,size=min(10000,simulations-start))
        stats=np.sum((simulated-expected)**2/expected,axis=1)
        exceed+=int(np.count_nonzero(stats>=stat-1e-12))
    return {'p':(exceed+1)/(simulations+1),'statistic':stat,'bins':len(groups),
            'minimum_expected':float(expected.min()),'mean_observed':float(np.mean(values)),
            'mean_expected':float(np.dot(np.arange(len(p)),p)),'simulations':simulations}


def analyze(dataset,simulations=200000):
    tests=[];summary={};rng=np.random.default_rng(SEED)
    def add(game,zone,family,label,**metrics):
        tests.append({'game':game,'zone':zone,'family':family,'label':label,**metrics})
    for game,rows in dataset['games'].items():
        assert len({r['issue'] for r in rows})==len(rows)
        assert rows==sorted(rows,key=lambda r:(r['date'],r['issue']))
        matrices={};summary[game]={'periods':len(rows),'first':rows[0],'last':rows[-1],'zones':{}}
        for zone,(maximum,count) in SPECS[game].items():
            numbers=np.array([r[zone] for r in rows]);n=len(rows)
            assert numbers.shape==(n,count)
            assert np.all((numbers>=1)&(numbers<=maximum))
            assert all(len(set(v))==count for v in numbers.tolist())
            x=np.zeros((n,maximum),dtype=np.int64)
            x[np.arange(n)[:,None],numbers-1]=1;matrices[zone]=x
            p=count/maximum;counts=x.sum(axis=0)
            for j,c in enumerate(counts):
                add(game,zone,'marginal',f'{j+1:02}',p=binomtest(int(c),n,p).pvalue,
                    observed=int(c),expected=n*p,rate=float(c/n),null_rate=p,relative_deviation=float(c/(n*p)-1))
            if count>1:
                joint=x.T@x;prob=count*(count-1)/(maximum*(maximum-1))
                for a in range(maximum):
                    for b in range(a+1,maximum):
                        c=int(joint[a,b]);add(game,zone,'pair',f'{a+1:02}+{b+1:02}',p=binomtest(c,n,prob).pvalue,observed=c,expected=n*prob)
            blocks=np.array_split(x,5)
            sizes=np.array([len(b) for b in blocks]);totals=np.array([b.sum(axis=0) for b in blocks])
            for j in range(maximum):
                table=np.stack([totals[:,j],sizes-totals[:,j]])
                stat,pvalue,_,expected=chi2_contingency(table,correction=False)
                add(game,zone,'time_blocks',f'{j+1:02}',p=float(pvalue),statistic=float(stat),minimum_expected=float(expected.min()),block_counts=totals[:,j].tolist(),block_sizes=sizes.tolist())
            for lag in range(1,11):
                overlap=np.sum(x[:-lag]*x[lag:],axis=1)
                result=goodness(overlap,hypergeom.pmf(np.arange(count+1),maximum,count,count),rng,simulations)
                if result:add(game,zone,'lag_overlap',str(lag),**result)
            distributions=[('sum',numbers.sum(axis=1),sum_pmf(maximum,count)),
                           ('odd',np.sum(numbers%2,axis=1),hypergeom.pmf(np.arange(count+1),maximum,(maximum+1)//2,count)),
                           ('adjacent',np.sum(np.diff(np.sort(numbers,axis=1),axis=1)==1,axis=1),adjacent_pmf(maximum,count))]
            for family,values,probabilities in distributions:
                result=goodness(values,probabilities,rng,simulations)
                if result:add(game,zone,family,'distribution',**result)
            high=np.argsort(-counts)[:3];low=np.argsort(counts)[:3]
            summary[game]['zones'][zone]={'maximum':maximum,'pick':count,'expected_per_number':n*count/maximum,
                'high':[{'number':int(i+1),'count':int(counts[i])} for i in high],
                'low':[{'number':int(i+1),'count':int(counts[i])} for i in low],
                'lag1_observed':float(np.mean(np.sum(x[:-1]*x[1:],axis=1))), 'lag1_expected':count*count/maximum,
                'blocks':[{'from':rows[sum(sizes[:i])]['date'],'to':rows[sum(sizes[:i+1])-1]['date'],'periods':int(sizes[i])} for i in range(5)]}
            print(game,zone,'finished',flush=True)
        front,back=matrices['front'],matrices['back'];joint=front.T@back
        prob=SPECS[game]['front'][1]/SPECS[game]['front'][0]*SPECS[game]['back'][1]/SPECS[game]['back'][0]
        for a in range(front.shape[1]):
            for b in range(back.shape[1]):
                c=int(joint[a,b]);add(game,'cross','cross_pair',f'{a+1:02}+{b+1:02}',p=binomtest(c,len(rows),prob).pvalue,observed=c,expected=len(rows)*prob)
    corrected=holm([t['p'] for t in tests])
    for t,p in zip(tests,corrected):t['holm_p']=float(p)
    return {'seed':SEED,'simulations':simulations,'total_tests':len(tests),'raw_below_005':int(sum(t['p']<.05 for t in tests)),
            'significant':[t for t in tests if t['holm_p']<.05],'summary':summary,'tests':tests}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('dataset');parser.add_argument('--simulations',type=int,default=200000)
    args=parser.parse_args();path=Path(args.dataset);raw=path.read_bytes();data=json.loads(raw)
    result=analyze(data,args.simulations);result['dataset_sha256']=hashlib.sha256(raw).hexdigest()
    (path.parent/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    with (path.parent/'tests.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=['game','zone','family','label','p','holm_p','observed','expected','statistic'],extrasaction='ignore');writer.writeheader();writer.writerows(result['tests'])
    print(json.dumps({k:v for k,v in result.items() if k not in ('tests','summary')},ensure_ascii=False),flush=True)
    print('lowest',json.dumps(sorted(result['tests'],key=lambda t:t['p'])[:12],ensure_ascii=False),flush=True)

if __name__=='__main__':main()
