"""Versioned descriptive features. No fitting, ticket generation or persistence."""
from collections import Counter
from itertools import combinations, groupby
import hashlib
import json
import math
import numpy as np
from .domain import GAMES, canonical_issue, validate_ticket
from .indicators import omission_features, feature_sequence  # legacy training entrypoint, unchanged protocol

VERSION='descriptive-v1'
WINDOWS=(10,20,30,50,100,500,'all')
# A structured statistic is one catalog entry; its category encodings are not new indicators.
DEFINITIONS={
    'count': '号码在窗口中出现的期数 c',
    'frequency': 'c / n；n 为窗口内保留记录数',
    'hot_rank': '1 + 出现次数严格大于本号码的号码个数（并列同名次）',
    'cold_rank': '1 + 出现次数严格小于本号码的号码个数',
    'current_omission': 'n - 1 - 最后出现位置；未出现则 n，仅为窗口内下界',
    'left_censored': '窗口内未出现；当前遗漏真实长度未知',
    'max_omission': '相邻两次出现位置之差减1的最大值；只含完成间隔',
    'mean_omission': '完成遗漏间隔的算术平均',
    'omission_std': '完成遗漏间隔的总体标准差 ddof=0',
    'completed_intervals': '相邻出现对数 max(c-1,0)',
    'repeat_intervals': '相邻出现位置之差的次数分布（遗漏+1）',
    'frequency_z': '(c-n*p)/sqrt(n*p*(1-p))，p=区内球数/区内号码数；描述分数非显著性结论',
    'odd_even': '[奇数数量,偶数数量]',
    'odd_run': '排序号码的奇偶标签中最长相同标签连续段长度',
    'small_big': '[号码<=floor(M/2)数量,其余数量]',
    'size_run': '排序号码的大小标签中最长相同标签连续段长度',
    'thirds': '按 floor((号码-1)*3/M) 分箱的数量，顺序0..2',
    'fourths': '按 floor((号码-1)*4/M) 分箱的数量，顺序0..3',
    'thirds_density': '三区各箱球数 / 该箱可选号码总数',
    'fourths_density': '四区各箱球数 / 该箱可选号码总数',
    'sum': '号码之和',
    'mean': '号码算术平均',
    'median': '排序号码中位数',
    'variance': '号码总体方差 ddof=0',
    'span': '最大号码减最小号码',
    'tail_counts': '号码 mod 10 的数量分布，顺序0..9',
    'tail_sum': '各号码 mod 10 的和',
    'same_tail_pairs': '各尾数计数 t 的 t*(t-1)/2 之和',
    'consecutive_groups': '排序号码中长度>=2、相邻差为1的极大连续段个数',
    'max_consecutive': '排序号码中相邻差为1的最长段长度；无连号为1',
    'gaps': '排序相邻号码之差',
    'previous_repeat': '本期号码中也出现在上一保留记录的号码数',
    'previous_neighbors': '本期号码中与上一保留记录至少一个号码差1的号码数，每号最多计1',
    'previous_same_tail': '本期号码中与上一保留记录至少一个号码同尾的号码数，包含重号',
    'previous_differences': '本期排序号码减上一保留记录排序号码，按位置相减',
    'distinct_differences': '本期所有号码对的不同正差值个数',
    'ac': '不同正差值个数 - (本区球数-1)',
    'tail_entropy': '-sum(p_t*log2(p_t))；p_t 为本注各尾数占比，忽略0；单位bit',
    'prime_counts': '[1的数量,质数数量,合数数量]；1既非质数也非合数',
    'mod3': '号码 mod 3 的数量分布，顺序0,1,2',
    'cooccurrence': '二码/三码同期开奖次数 / n；仅返回至少出现一次的组合，其余次数为0。条件频率为共同次数/给定子集出现次数；非跨期预测',
}
NUMBER_IDS=set(list(DEFINITIONS)[:12])
PAIR_ONLY={'span','same_tail_pairs','consecutive_groups','max_consecutive','gaps','distinct_differences','ac'}
PREVIOUS_IDS={key for key in DEFINITIONS if key.startswith('previous_')}


def feature_catalog():
    features=[]
    for key,formula in DEFINITIONS.items():
        null='空历史没有组合行；计数0不代表未来概率为0'
        if key in NUMBER_IDS:
            null='无样本时频率/排名/Z/当前遗漏为null；无完成间隔时最大/平均/标准差为null，分布为空；计数为0'
        elif key in PAIR_ONLY:
            null='单球区为null，不将不适用显示为0'
        elif key in PREVIOUS_IDS:
            null='没有上一保留记录时为null'
        features.append({'id':key,'formula':formula,'version':VERSION,'windows':list(WINDOWS),
                         'zones':['front','back'],'null_semantics':null,
                         'dependencies':['previous_retained_draw'] if key in PREVIOUS_IDS else ['retained_draws'],
                         'shape':'number' if key in NUMBER_IDS else ('cooccurrence' if key=='cooccurrence' else 'combination')})
    return {'version':VERSION,'windows':list(WINDOWS),'features':features,
            'note':'历史描述不等于下期概率；分类编码和交互列不计作独立指标。条件频率来自同期开奖，稀疏分母即使为1也不代表确定性。'}


def _run(labels):
    return max(len(list(group)) for _,group in groupby(labels))


def combination_features(numbers, maximum, previous=None):
    if not numbers or len(set(numbers))!=len(numbers) or any(type(v) is not int or not 1<=v<=maximum for v in numbers):
        raise ValueError('Invalid combination')
    values=sorted(numbers); k=len(values)
    if previous is not None and (len(previous)!=k or len(set(previous))!=k or any(type(v) is not int or not 1<=v<=maximum for v in previous)):
        raise ValueError('Invalid previous combination')
    tails=[v%10 for v in values]; tail_counts=[tails.count(t) for t in range(10)]
    gaps=[b-a for a,b in zip(values,values[1:])]
    runs=[len(list(g)) for _,g in groupby(enumerate(values),lambda pair:pair[1]-pair[0])]
    differences={b-a for a,b in combinations(values,2)}
    result={
        'odd_even':[sum(v%2 for v in values),sum(v%2==0 for v in values)],
        'odd_run':_run([v%2 for v in values]),
        'small_big':[sum(v<=maximum//2 for v in values),sum(v>maximum//2 for v in values)],
        'size_run':_run([v>maximum//2 for v in values]),
        'sum':sum(values),'mean':float(np.mean(values)),'median':float(np.median(values)),
        'variance':float(np.var(values)),'span':values[-1]-values[0],
        'tail_counts':tail_counts,'tail_sum':sum(tails),'same_tail_pairs':sum(c*(c-1)//2 for c in tail_counts),
        'consecutive_groups':sum(r>=2 for r in runs),'max_consecutive':max(runs),'gaps':gaps,
        'distinct_differences':len(differences),'ac':len(differences)-(k-1),
        'tail_entropy':-sum(c/k*math.log2(c/k) for c in tail_counts if c),
        'prime_counts':[sum(v==1 for v in values),sum(v>=2 and all(v%d for d in range(2,math.isqrt(v)+1)) for v in values),0],
        'mod3':[sum(v%3==r for v in values) for r in range(3)],
    }
    result['prime_counts'][2]=k-sum(result['prime_counts'][:2])
    for name,bins in [('thirds',3),('fourths',4)]:
        counts=[sum((v-1)*bins//maximum==b for v in values) for b in range(bins)]
        sizes=[sum((v-1)*bins//maximum==b for v in range(1,maximum+1)) for b in range(bins)]
        result[name]=counts;result[name+'_density']=[c/s for c,s in zip(counts,sizes)]
    for key in PREVIOUS_IDS: result[key]=None
    if previous is not None:
        result.update(previous_repeat=len(set(values)&set(previous)),
                      previous_neighbors=sum(any(abs(v-p)==1 for p in previous) for v in values),
                      previous_same_tail=sum(any(v%10==p%10 for p in previous) for v in values),
                      previous_differences=[v-p for v,p in zip(values,sorted(previous))])
    if k==1:
        for key in PAIR_ONLY: result[key]=None
    return result


def analyze_features(rows, game, zone, cutoff_issue, window='all'):
    """Inclusive issue cutoff; caller supplies a retained-as-of or revised snapshot.

    Gap units are records, never calendar days. No inferred draws fill archive holes.
    """
    if game not in GAMES or zone not in ('front','back') or window not in WINDOWS:
        raise ValueError('Invalid game, zone or window')
    cutoff_issue=canonical_issue(cutoff_issue)
    selected=sorted((r for r in rows if canonical_issue(r['issue'])<=cutoff_issue),key=lambda r:canonical_issue(r['issue']))
    if len({canonical_issue(r['issue']) for r in selected})!=len(selected):
        raise ValueError('Duplicate issue')
    for row in selected:
        if row.get('conflict'): raise ValueError('Unresolved source conflict')
        validate_ticket(game,row['front'],row['back'])
    available=len(selected)
    if window!='all': selected=selected[-window:]
    maximum,k=GAMES[game][zone];n=len(selected)
    matrix=np.zeros((n,maximum))
    for i,row in enumerate(selected): matrix[i,np.array(row[zone])-1]=1
    omissions=omission_features(matrix);counts=matrix.sum(axis=0).astype(int)
    numbers=[];p=k/maximum
    for j,c in enumerate(counts):
        positions=np.flatnonzero(matrix[:,j]);intervals=np.diff(positions);gaps=intervals-1
        numbers.append({'number':j+1,'count':int(c),'frequency':float(c/n) if n else None,
            'hot_rank':int(1+sum(counts>c)) if n else None,'cold_rank':int(1+sum(counts<c)) if n else None,
            'current_omission':int(omissions[j,0]) if n else None,'left_censored':bool(omissions[j,4]),
            'max_omission':int(omissions[j,1]) if len(gaps) else None,
            'mean_omission':float(omissions[j,2]) if len(gaps) else None,
            'omission_std':float(np.std(gaps)) if len(gaps) else None,'completed_intervals':len(gaps),
            'repeat_intervals':[{'interval':int(v),'count':c} for v,c in sorted(Counter(intervals).items())],
            'frequency_z':float((c-n*p)/math.sqrt(n*p*(1-p))) if n else None})
    combos=[];joint=Counter();singles=Counter()
    for i,row in enumerate(selected):
        chosen=sorted(row[zone]);singles.update(chosen)
        for size in (2,3): joint.update(combinations(chosen,size))
        combos.append({'issue':row['issue'],'features':combination_features(chosen,maximum,selected[i-1][zone] if i else None)})
    cooccurrence=[]
    for chosen,count in sorted(joint.items(),key=lambda item:(len(item[0]),item[0])):
        given_sets=[(v,) for v in chosen] if len(chosen)==2 else [tuple(v for v in chosen if v!=excluded) for excluded in chosen]
        conditional=[]
        for given in given_sets:
            denominator=singles[given[0]] if len(given)==1 else joint[given]
            conditional.append({'given':list(given),'denominator':denominator,'frequency':count/denominator})
        cooccurrence.append({'numbers':list(chosen),'count':count,'frequency':count/n,'conditional':conditional})
    digest=hashlib.sha256(json.dumps([{'issue':canonical_issue(r['issue']),'numbers':sorted(r[zone])} for r in selected],sort_keys=True).encode()).hexdigest()
    return {'version':VERSION,'game':game,'zone':zone,'cutoff_issue':cutoff_issue,'window':window,
            'sample_size':n,'available_records':available,'short_window':window!='all' and n<window,
            'first_issue':selected[0]['issue'] if n else None,'last_issue':selected[-1]['issue'] if n else None,
            'dataset_hash':digest,'numbers':numbers,'combinations':combos,'cooccurrence':cooccurrence,
            'notes':['窗口按保留记录计数，不能证明官方连续全量覆盖；遗漏单位为记录。',
                     '完成间隔排除窗口首尾未完成区间；未出现号码的当前遗漏为窗口内下界。',
                     '共现仅列非零组合；同期开奖条件频率不是下期概率，少样本中的0或1不代表确定性。']}
