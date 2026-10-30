import { SimulationPanel } from './SimulationPanel';
import { useState } from 'react';
import { Button } from '@heroui/react';
import { get, type Game } from '../api';
type Result={units:number;zone_units:number[];cost:number;unit_cost:number;note:string;config:unknown;tickets:{front:number[];back:number[]}[];draw_fingerprint?:string;
  settlement?:{issue:string;rule_version:string;known_return:string;pending:number;net:string|null;note:string;
    results:{ticket:{front:number[];back:number[]};level:number|null;basic_amount:string|null;additional_amount:string|null;amount:string|null}[]}};
export function CombinationPanel({game,adminName}:{game:Game;adminName?:string}){
  const [kind,setKind]=useState('single');const [front,setFront]=useState('');const [back,setBack]=useState('');
  const [frontBankers,setFrontBankers]=useState('');const [backBankers,setBackBankers]=useState('');
  const [additional,setAdditional]=useState(false);const [issue,setIssue]=useState('');
  const [result,setResult]=useState<Result|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);
  function numbers(s:string){if(!s.trim())return [];const parts=s.trim().split(/[\s,，]+/);if(parts.some(p=>!/^\d+$/.test(p)))throw Error('号码仅允许整数，以空格或逗号分隔');return parts.map(Number);}
  async function run(e:React.FormEvent){e.preventDefault();setError('');setResult(null);setBusy(true);
    try{const config={game,kind,front:numbers(front),back:numbers(back),front_bankers:kind==='banker'?numbers(frontBankers):[],back_bankers:kind==='banker'?numbers(backBankers):[],additional};
      const query=new URLSearchParams({config:JSON.stringify(config)});if(issue)query.set('issue',issue);
      setResult(await get<Result>('/research/combinations?'+query));
    }catch(e){setError(String(e));}finally{setBusy(false);}}
  return <section className="panel archive-panel"><h2>组合计费与模拟结算</h2><p>单式、复式、胆拖最多展开2000注；不支持倍数。结果不加入正式预测，不影响每彩种5注建议。</p>
    <form onSubmit={run} onChange={()=>setResult(null)}><fieldset disabled={busy} className="archive-filters"><legend>号码设置</legend>
      <label>票型<select value={kind} onChange={e=>setKind(e.target.value)}><option value="single">单式</option><option value="multiple">复式</option><option value="banker">胆拖</option></select></label>
      <label>{game==='ssq'?'红球':'前区'}{kind==='banker'?'拖码（无胆时填全部选号）':'选号'}<input required value={front} onChange={e=>setFront(e.target.value)} placeholder="01 02 03…"/></label>
      <label>{game==='ssq'?'蓝球':'后区'}{kind==='banker'?'拖码（无胆时填全部选号）':'选号'}<input required value={back} onChange={e=>setBack(e.target.value)}/></label>
      {kind==='banker' && <><label>{game==='ssq'?'红球':'前区'}胆码<input value={frontBankers} onChange={e=>setFrontBankers(e.target.value)}/></label>{game==='dlt' && <label>后区胆码<input value={backBankers} onChange={e=>setBackBankers(e.target.value)}/></label>}</>}
      {game==='dlt' && <label><input type="checkbox" checked={additional} onChange={e=>setAdditional(e.target.checked)}/>追加（每注多1元）</label>}
      <label>模拟开奖期号（留空只计费）<input pattern="[0-9]{7}" value={issue} onChange={e=>setIssue(e.target.value)} placeholder="2026120"/></label>
      <Button type="submit" isDisabled={busy}>{busy?'计算中…':'计算组合与模拟结果'}</Button>
    </fieldset></form><p>单式每注2元；追加每注合计3元。胆拖至少一区有胆码，胆码拖码不重叠，设胆区总号码须超过单式数量。追加结算仅支持2019019及以后的一、二等奖规则。</p>
    {error && <p role="alert">{error}</p>}{result && <div><h3>{result.zone_units.join(' × ')} = {result.units} 注 · 每注¥{result.unit_cost} · 模拟成本¥{result.cost}</h3><p>{result.note}</p>
      {result.settlement && <><p>第{result.settlement.issue}期 · {result.settlement.rule_version} · 已确认奖金¥{result.settlement.known_return} · 待确认{result.settlement.pending}注 · 净收益{result.settlement.net==null?'待确认':`¥${result.settlement.net}`}</p><p>{result.settlement.note}</p></>}
      <details><summary>展开单式与逐注结算（{result.units}注）</summary><div className="table-scroll"><table className="experiment-table"><thead><tr><th>序号</th><th>前区 / 红球</th><th>后区 / 蓝球</th><th>奖级</th><th>基本 / 追加 / 合计奖金</th></tr></thead><tbody>{result.tickets.map((t,i)=>{const r=result.settlement?.results[i];return <tr key={i}><td>{i+1}</td><td>{t.front.join(' ')}</td><td>{t.back.join(' ')}</td><td>{r?(r.level??'未中奖'):'未结算'}</td><td>{r?[r.basic_amount,r.additional_amount,r.amount].map(a=>a??'待确认').join(' / '):'—'}</td></tr>;})}</tbody></table></div></details>
      <details><summary>原始配置与结果（含开奖指纹）</summary><pre className="model-json">{JSON.stringify(result,null,2)}</pre></details>
    </div>}
    <SimulationPanel ticket={result?.config} adminName={adminName}/>
  </section>;
}
