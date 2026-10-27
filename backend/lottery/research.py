"""Bounded constraint experiments; never create official forecasts or evidence."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .domain import GAMES
from .feature_service import VERSION as FEATURE_VERSION, combination_features
from .selection import select_tickets, selection_metadata, UNIFORM

SmallInt=Annotated[int,Field(strict=True,ge=0,le=6)]
Bound=Annotated[int,Field(strict=True,ge=0,le=210)]


class ZoneConstraints(BaseModel):
    model_config=ConfigDict(extra='forbid')
    odd: SmallInt | None=None
    small: SmallInt | None=None
    thirds: tuple[SmallInt,SmallInt,SmallInt] | None=None
    fourths: tuple[SmallInt,SmallInt,SmallInt,SmallInt] | None=None
    sum_min: Bound | None=None
    sum_max: Bound | None=None
    span_min: Bound | None=None
    span_max: Bound | None=None

    @model_validator(mode='after')
    def ranges(self):
        for name in ('sum','span'):
            low=getattr(self,name+'_min');high=getattr(self,name+'_max')
            if low is not None and high is not None and low>high:
                raise ValueError('下限不能大于上限')
        return self


class ResearchConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    game: Literal['ssq','dlt']
    seed: Annotated[int,Field(strict=True,ge=0,le=2147483647)]
    count: Annotated[int,Field(strict=True,ge=1,le=10)]=5
    pool_size: Annotated[int,Field(strict=True,ge=1,le=2000)]=2000
    front: ZoneConstraints=Field(default_factory=ZoneConstraints)
    back: ZoneConstraints=Field(default_factory=ZoneConstraints)

    @model_validator(mode='after')
    def single_ball(self):
        if self.game=='ssq' and (self.back.span_min is not None or self.back.span_max is not None):
            raise ValueError('双色球蓝球为单球区，不适用跨度约束')
        return self


def impossible(config):
    for zone in ('front','back'):
        maximum,k=GAMES[config.game][zone];rules=getattr(config,zone)
        for field,available in [('odd',(maximum+1)//2),('small',maximum//2)]:
            value=getattr(rules,field)
            if value is not None and not max(0,k-(maximum-available))<=value<=min(k,available):
                return f'{zone}：{field}数量与本区可选号码冲突'
        for field,bins in [('thirds',3),('fourths',4)]:
            values=getattr(rules,field)
            if values is not None:
                sizes=[sum((v-1)*bins//maximum==b for v in range(1,maximum+1)) for b in range(bins)]
                if sum(values)!=k or any(c>size for c,size in zip(values,sizes)):
                    return f'{zone}：分区数量之和必须等于本区选球数，且不能超过各区容量'
        for field,low,high in [('sum',k*(k+1)//2,k*(2*maximum-k+1)//2),('span',k-1,maximum-1)]:
            lower=getattr(rules,field+'_min');upper=getattr(rules,field+'_max')
            if (lower is not None and lower>high) or (upper is not None and upper<low):
                return f'{zone}：{field}约束不在理论可行范围 {low}–{high}'
    return None


def matches(features,rules):
    for key,actual in [('odd',features['odd_even'][0]),('small',features['small_big'][0]),('thirds',features['thirds']),('fourths',features['fourths'])]:
        expected=getattr(rules,key)
        if expected is not None and (list(expected) if isinstance(expected,tuple) else expected)!=actual:return False
    for name in ('sum','span'):
        low=getattr(rules,name+'_min');high=getattr(rules,name+'_max')
        if low is not None and features[name]<low:return False
        if high is not None and features[name]>high:return False
    return True


def research_selection(request):
    config=ResearchConfig.model_validate(request)
    result={'version':'research-constraints-v1','mode':'research-only','config':config.model_dump(mode='json'),
            'selection':selection_metadata(UNIFORM),'feature_version':FEATURE_VERSION,
            'candidate_seed_rule':'seed + attempt_index (starting at zero)',
            'budget':config.count*2,'tickets':[],'attempts':0,'matched_count':0,
            'note':'仅模拟研究；约束描述号码结构，不代表提升中奖概率。不进入正式推荐或前瞻评分。'}
    reason=impossible(config)
    if reason:return {**result,'status':'infeasible','message':reason}
    found=[];seen=set()
    for index in range(config.pool_size):
        ticket=select_tickets(config.game,config.seed+index,count=1)[0]
        result['attempts']=index+1
        signature=tuple(ticket['front']+ticket['back'])
        if signature in seen:continue
        seen.add(signature)
        if all(matches(combination_features(ticket[zone],GAMES[config.game][zone][0]),getattr(config,zone)) for zone in ('front','back')):
            found.append(ticket)
        if len(found)==config.count:
            return {**result,'status':'complete','message':'已找到满足约束的研究票组','matched_count':len(found),'tickets':found}
    return {**result,'status':'exhausted','message':'候选搜索已达到上限，未找到足够票组；这不能证明约束无解。请放宽条件或更换种子。','matched_count':len(found)}
