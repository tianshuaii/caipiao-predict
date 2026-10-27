"""Exploratory intervals, not sequential evidence or future prediction intervals."""
import math
from decimal import Decimal
import numpy as np

VERSION='uncertainty-block-v1'
SEED=20261027
REPLICATES=2000
BLOCK_LENGTH=5
MIN_PERIODS=30


def rate_interval(successes,periods):
    if type(successes) is not int or type(periods) is not int or not 0<=successes<=periods:
        raise ValueError('Invalid binomial counts')
    interval=None
    if periods:
        z=1.959963984540054;p=successes/periods;denom=1+z*z/periods
        center=(p+z*z/(2*periods))/denom
        half=z*math.sqrt(p*(1-p)/periods+z*z/(4*periods**2))/denom
        interval=[0.0 if successes==0 else max(0.,center-half),1.0 if successes==periods else min(1.,center+half)]
    return {'method':'Wilson','confidence':.95,'successes':successes,'periods':periods,
            'sample_unit':'draw','interval':interval,
            'assumption':'探索性固定概率、独立期次近似；不保证自适应或相关序列覆盖率，不用于持续检验或晋升。'}


def block_interval(issues,values):
    if len(issues)!=len(values) or issues!=sorted(set(issues)):
        raise ValueError('Expected unique chronological issues and aligned values')
    x=np.asarray(values,dtype=float)
    if not np.isfinite(x).all(): raise ValueError('Finite differences required')
    n=len(x)
    result={'method':'moving-block-percentile-bootstrap','confidence':.95,'sample_unit':'draw-block',
            'block_length':BLOCK_LENGTH,'replicates':REPLICATES,'replicates_performed':0,'segments':[],'seed':SEED,'periods':n,'issues':issues,
            'estimate':float(x.mean()) if n else None,'interval':None,'reason':None}
    if n<MIN_PERIODS: return {**result,'reason':'insufficient_periods'}
    if np.all(x==x[0]): return {**result,'reason':'constant_observed_difference'}
    # Never bridge missing issues or a year boundary whose last issue is unknown.
    starts=[0]+[i for i in range(1,n) if issues[i][:4]!=issues[i-1][:4] or int(issues[i])!=int(issues[i-1])+1]+[n]
    if any(b-a<BLOCK_LENGTH for a,b in zip(starts,starts[1:])):
        return {**result,'reason':'short_contiguous_segment'}
    segments=list(zip(starts,starts[1:]))
    result['segments']=[{'from_issue':issues[a],'to_issue':issues[b-1],'periods':b-a} for a,b in segments]
    blocks=[np.asarray([np.arange(i,i+BLOCK_LENGTH) for i in range(a,b-BLOCK_LENGTH+1)]) for a,b in segments]
    rng=np.random.default_rng(SEED)
    means=[]
    for _ in range(REPLICATES):
        indices=np.concatenate([bank[rng.integers(len(bank),size=math.ceil((b-a)/BLOCK_LENGTH))].reshape(-1)[:b-a]
                                for (a,b),bank in zip(segments,blocks)])
        means.append(float(x[indices].mean()))
    result['replicates_performed']=REPLICATES
    if all(value==means[0] for value in means):
        return {**result,'reason':'degenerate_resampling_distribution'}
    return {**result,'interval':np.quantile(means,[.025,.975]).tolist()}


def paired_uncertainty(matched,controls,money):
    matched=sorted(matched);money=sorted(money)
    def interval(rows,metric):
        def value(group):
            if metric in ('any_prize','first_prize'):return float(group[metric])
            return float(Decimal(group['known_return'])-Decimal(str(group['cost'])))
        differences=[value(m)-sum(value(g) for g in controls[i])/len(controls[i]) for i,m in rows]
        return block_interval([i for i,_ in rows],differences)
    first=interval(matched,'first_prize')
    event_periods=sum(m['first_prize'] or any(g['first_prize'] for g in controls[i]) for i,m in matched)
    if event_periods<5: first={**first,'interval':None,'reason':'rare_first_prize_events'}
    return {'version':VERSION,'control_groups':100,'comparison':'strategy-minus-mean-of-frozen-controls',
            'any_prize':interval(matched,'any_prize'),'first_prize':{**first,'event_periods':event_periods},
            'net_per_period':interval(money,'net'),
            'note':'整期配对，100组对照先在同一期求均值，不视为100个独立期次。块区间依赖近似平稳及弱相关假设；不是未来预测区间，也不是晋升证据。收益仅条件于双方奖金完整的相同期次，经验重采样无法识别未观察到的稀有巨奖尾部。'}
