"""Independent historical virtual accounts. No writes to prediction evidence."""
import hashlib
import json
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from .combinations import TicketConfig, expand, simulate
from .domain import canonical_issue

VERSION='virtual-account-v1'
Money=Decimal

class SimulationConfig(BaseModel):
    model_config=ConfigDict(extra='forbid')
    ticket:TicketConfig
    start_issue:str=Field(pattern=r'^[0-9]{7}$')
    periods:int=Field(default=10,ge=1,le=30,strict=True)
    initial_balance:Money=Field(default=Decimal('1000'),gt=0,le=1000000,max_digits=9,decimal_places=2)
    budget:Money=Field(default=Decimal('100'),gt=0,le=1000000,max_digits=9,decimal_places=2)
    stop_loss:Money|None=Field(default=None,gt=0,le=1000000,max_digits=9,decimal_places=2)
    stop_on_win:bool=Field(default=False,strict=True)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def run_simulation(value,snapshot):
    c=SimulationConfig.model_validate(value);canonical_issue(c.start_issue)
    ticket=c.ticket.model_dump();preview=expand(ticket)
    if preview['units']*c.periods>20000:raise ValueError('模拟最多20000个单式期次结算')
    cost=Decimal(preview['cost']);balance=c.initial_balance;spent=Decimal(0);returns=Decimal(0)
    ledger=[{'issue':None,'kind':'opening','amount':str(balance),'balance':str(balance)}]
    rounds=[];reason='period_limit';pending=False
    for index in range(c.periods):
        if balance<cost:reason='insufficient_balance';break
        if spent+cost>c.budget:reason='budget_limit';break
        if c.stop_loss is not None and c.initial_balance-balance+cost>c.stop_loss:reason='loss_limit';break
        if index>=len(snapshot):reason='missing_draw';break
        row=snapshot[index];draw=row['data'];issue=draw['issue']
        expected=f'{int(c.start_issue)+index:07d}'
        if issue[:4]!=c.start_issue[:4]:reason='year_boundary';break
        if issue!=expected:reason='missing_draw';break
        if row['conflict']:reason='draw_conflict';break
        settlement=simulate(ticket,draw)['settlement']
        balance-=cost;spent+=cost
        ledger.append({'issue':issue,'kind':'purchase','amount':str(-cost),'balance':str(balance)})
        known=Decimal(settlement['known_return']);balance+=known;returns+=known
        ledger.append({'issue':issue,'kind':'prize','amount':str(known),'balance':str(balance),'pending_tickets':settlement['pending']})
        rounds.append({'issue':issue,'draw_fingerprint':row['fingerprint'],**settlement})
        if settlement['pending']:reason='amount_pending';pending=True;break
        if c.stop_on_win and any(r['level'] is not None for r in settlement['results']):reason='win';break
        if c.stop_loss is not None and c.initial_balance-balance>=c.stop_loss:reason='loss_limit';break
    return {'version':VERSION,'config':c.model_dump(mode='json'),'played':len(rounds),'stop_reason':reason,
            'balance':str(balance),'spent':str(spent),'known_return':str(returns),'pending':pending,
            'net':None if pending else str(balance-c.initial_balance),'ledger':ledger,'rounds':rounds,
            'note':'当前修订历史数据的固定号码模拟，非前瞻验证；余额仅含已确认奖金。无真实交易，不改变正式推荐。'}


def create_simulation(db,config):
    from sqlalchemy import select
    from .models import Draw,SimulationRun
    value=config.model_dump(mode='json')
    # Validate bounded computation before querying or storing.
    run_simulation(value,[])
    rows=db.scalars(select(Draw).where(Draw.game==config.ticket.game,Draw.issue>=config.start_issue).order_by(Draw.issue).limit(config.periods))
    snapshot=[{'data':r.data,'conflict':r.conflict,'fingerprint':r.fingerprint} for r in rows]
    result=run_simulation(value,snapshot)
    row=SimulationRun(version=VERSION,config=value,snapshot=snapshot,snapshot_hash=digest(snapshot),result=result,result_hash=digest(result))
    db.add(row);db.commit();db.refresh(row)
    return row


def replay(row):
    if row.version!=VERSION:raise ValueError('模拟版本不兼容，拒绝重放')
    if digest(row.snapshot)!=row.snapshot_hash or digest(row.result)!=row.result_hash:raise ValueError('快照或结果完整性校验失败')
    result=run_simulation(row.config,row.snapshot)
    return {'id':row.id,'matches':digest(result)==row.result_hash,'result':result}


def view(row,detail=False):
    return {'id':row.id,'created_at':row.created_at.isoformat()+'Z','version':row.version,
            'config':row.config,'snapshot_hash':row.snapshot_hash,'result_hash':row.result_hash,
            'result':row.result if detail else {k:row.result[k] for k in ('played','stop_reason','balance','spent','net','pending')},
            **({'snapshot':row.snapshot} if detail else {})}
