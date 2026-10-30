"""Bounded compound-ticket simulations, independent of official recommendations."""
from decimal import Decimal, ROUND_DOWN
from itertools import combinations, product
from math import comb
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from .domain import GAMES, canonical_issue, rule_version
from .settlement import settle_ticket

MAX_UNITS=2000

class TicketConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    game:Literal['ssq','dlt']
    kind:Literal['single','multiple','banker']
    front:list[StrictInt]=Field(max_length=35)
    back:list[StrictInt]=Field(max_length=16)
    front_bankers:list[StrictInt]=Field(default_factory=list,max_length=4+1)
    back_bankers:list[StrictInt]=Field(default_factory=list,max_length=1)
    additional:bool=Field(default=False,strict=True)


def expand(value):
    c=TicketConfig.model_validate(value)
    if c.additional and c.game!='dlt':raise ValueError('双色球不支持追加')
    if c.kind!='banker' and (c.front_bankers or c.back_bankers):raise ValueError('仅胆拖可填写胆码')
    if c.kind=='banker' and not (c.front_bankers or c.back_bankers):raise ValueError('胆拖至少一区有胆码')
    zones=[];counts=[]
    for zone in ('front','back'):
        maximum,needed=GAMES[c.game][zone]
        numbers=getattr(c,zone);bankers=getattr(c,zone+'_bankers')
        if len(set(numbers+bankers))!=len(numbers+bankers):raise ValueError('号码重复或胆码拖码重叠')
        if any(not 1<=n<=maximum for n in numbers+bankers):raise ValueError('号码超出范围')
        if len(bankers)>=needed:raise ValueError('胆码必须少于本区单式球数')
        if len(numbers)+len(bankers)<needed:raise ValueError('所选号码不足')
        if bankers and len(numbers)+len(bankers)<=needed:raise ValueError('胆码与拖码总数必须超过本区单式球数')
        counts.append(comb(len(numbers),needed-len(bankers)))
        zones.append((sorted(bankers),sorted(numbers),needed-len(bankers)))
    units=counts[0]*counts[1]
    if c.kind=='single' and units!=1:raise ValueError('单式只能包含一注')
    if c.kind=='multiple' and units<=1:raise ValueError('复式至少一选号区超过单式数量')
    if units>MAX_UNITS:raise ValueError(f'组合数{units}超过模拟上限{MAX_UNITS}注')
    pools=[[sorted(b+list(t)) for t in combinations(n,k)] for b,n,k in zones]
    tickets=[{'front':f,'back':b} for f,b in product(*pools)]
    return {'config':c.model_dump(),'units':units,'zone_units':counts,'unit_cost':3 if c.additional else 2,
            'cost':units*(3 if c.additional else 2),'tickets':tickets,'max_units':MAX_UNITS,
            'note':'仅模拟，不购买、不加入正式建议；每彩种正式推荐仍5注单式。'}


def simulate(value,draw=None):
    result=expand(value)
    if draw is None:return result
    c=result['config'];issue=canonical_issue(draw['issue'])
    if c['additional'] and issue<'2019019':raise ValueError('追加结算仅支持大乐透2019019及以后规则')
    entries=[];known=Decimal(0);pending=0
    for ticket in result['tickets']:
        base=settle_ticket(c['game'],ticket,draw)
        amount=Decimal(base['amount']) if base['amount'] is not None else None
        extra=Decimal(0)
        if c['additional'] and base['level'] in (1,2):
            extra=(amount*Decimal('0.8')).quantize(Decimal('1'),rounding=ROUND_DOWN) if amount is not None else None
        total=amount+extra if amount is not None and extra is not None else None
        if total is None:pending+=1
        else:known+=total
        entries.append({**base,'ticket':ticket,'basic_amount':base['amount'],
                        'additional_amount':str(extra) if extra is not None else None,'amount':str(total) if total is not None else None})
    result['settlement']={'issue':issue,'rule_version':rule_version(c['game'],issue),'results':entries,
        'known_return':str(known),'pending':pending,'net':str(known-result['cost']) if not pending else None,
        'additional_rule':'dlt-2019019-plus-80pct-floor-yuan' if c['additional'] else None,
        'note':'税前模拟：基本奖金取开奖公告；追加仅一/二等奖按基本奖金80%向下取整至元。未模拟促销派奖，不作为实际兑奖金额。'}
    return result
