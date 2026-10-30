import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get } from '../api';
import { adminRequest } from '../auth';
const reasons:Record<string,string>={period_limit:'达到期数',insufficient_balance:'余额不足',budget_limit:'达到预算上限',loss_limit:'达到亏损限制',missing_draw:'缺少连续开奖',draw_conflict:'开奖来源冲突',amount_pending:'奖金待确认',win:'中奖停止',year_boundary:'跨年需另建模拟'};
type Run={id:number;created_at:string;config:unknown;result:{played:number;stop_reason:string;balance:string;spent:string;net:string|null;pending:boolean;ledger?:{issue:string|null;kind:string;amount:string;balance:string;pending_tickets?:number}[]}};
export function SimulationPanel({ticket,adminName}:{ticket:unknown;adminName?:string}){
  const [start,setStart]=useState('');const [periods,setPeriods]=useState('10');const [initial,setInitial]=useState('1000');const [budget,setBudget]=useState('100');const [loss,setLoss]=useState('');const [win,setWin]=useState(false);
  const [rows,setRows]=useState<Run[]>([]);const [total,setTotal]=useState(0);const [offset,setOffset]=useState(0);const [revision,setRevision]=useState(0);const [detail,setDetail]=useState<Run|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [check,setCheck]=useState('');
  useEffect(()=>{const c=new AbortController();get<{items:Run[];total:number}>(`/simulations?offset=${offset}`,c.signal).then(r=>{if(!c.signal.aborted){setRows(r.items);setTotal(r.total);}}).catch(e=>{if(!c.signal.aborted)setError(String(e));});return()=>c.abort();},[offset,revision]);
  async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setCheck('');try{const r=await adminRequest<Run>('/simulations',{method:'POST',body:JSON.stringify({ticket,start_issue:start,periods:Number(periods),initial_balance:initial,budget,stop_loss:loss||null,stop_on_win:win})});setDetail(r);setOffset(0);setRevision(v=>v+1);}catch(e){setError(String(e));}finally{setBusy(false);}}
  async function load(id:number,replay=false){setBusy(true);setError('');setCheck('');try{if(replay){const r=await get<{matches:boolean}>(`/simulations/${id}?replay=true`);setCheck(r.matches?'冻结数据重放一致':'重放结果不一致，旧结果已保留');}else setDetail(await get<Run>(`/simulations/${id}`));}catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="archive-panel"><h2>虚拟账户与历史追号</h2><p>先在上方计算组合，再使用该固定票组建立独立账户。最多30期、20000个单式期次结算，不加倍、不充值、不实际购买。</p><p>仅管理员可保存；列表公开可读。缺期、冲突、未知奖金或跨年时停止。亏损上限按初始资金减已确认余额计算，购票前预留整期成本。</p>
    <form onSubmit={submit}><fieldset disabled={busy||!adminName||!ticket} className="archive-filters"><legend>独立账户设置</legend>
      <label>起始历史期号<input required pattern="[0-9]{7}" value={start} onChange={e=>setStart(e.target.value)}/></label>
      <label>最多期数<input type="number" required min="1" max="30" value={periods} onChange={e=>setPeriods(e.target.value)}/></label>
      <label>初始虚拟资金<input type="number" required min="0.01" max="1000000" step="0.01" value={initial} onChange={e=>setInitial(e.target.value)}/></label>
      <label>总支出预算<input type="number" required min="0.01" max="1000000" step="0.01" value={budget} onChange={e=>setBudget(e.target.value)}/></label>
      <label>累计亏损上限（可留空）<input type="number" min="0.01" max="1000000" step="0.01" value={loss} onChange={e=>setLoss(e.target.value)}/></label>
      <label><input type="checkbox" checked={win} onChange={e=>setWin(e.target.checked)}/>任意奖即停止</label><Button type="submit" isDisabled={busy||!adminName||!ticket}>保存新模拟</Button>
    </fieldset></form>{error&&<p role="alert">{error}</p>}
    <h3>历史模拟（所有彩种）</h3><div className="table-scroll"><table className="experiment-table"><thead><tr><th>编号</th><th>已模拟期数</th><th>停止原因</th><th>余额 / 支出</th><th>查看</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td>#{r.id}</td><td>{r.result.played}</td><td>{reasons[r.result.stop_reason]}</td><td>{r.result.balance} / {r.result.spent}</td><td><Button isDisabled={busy} onPress={()=>load(r.id)}>流水</Button></td></tr>)}</tbody></table></div>
    <p>共{total}项 <Button isDisabled={busy||offset===0} onPress={()=>setOffset(v=>v-20)}>上一页</Button><Button isDisabled={busy||offset+20>=total} onPress={()=>setOffset(v=>v+20)}>下一页</Button></p>
    {detail&&<div><h3>账户 #{detail.id} · {reasons[detail.result.stop_reason]}</h3><p>已确认余额 ¥{detail.result.balance} · 净收益 {detail.result.net??'待确认'}{detail.result.pending?'（存在未确认奖金）':''}</p><Button isDisabled={busy} onPress={()=>load(detail.id,true)}>按冻结快照重放核对</Button><p role="status">{check}</p><div className="table-scroll"><table className="experiment-table"><thead><tr><th>期号</th><th>类型</th><th>变动</th><th>余额</th></tr></thead><tbody>{detail.result.ledger?.map((r,i)=><tr key={i}><td>{r.issue??'初始'}</td><td>{{opening:'开户',purchase:'模拟支出',prize:'已确认奖金'}[r.kind]}{r.pending_tickets?`（${r.pending_tickets}注待确认）`:''}</td><td>{r.amount}</td><td>{r.balance}</td></tr>)}</tbody></table></div><details><summary>冻结配置、快照、逐注结算及校验信息</summary><pre className="model-json">{JSON.stringify(detail,null,2)}</pre></details></div>}
  </section>;
}
