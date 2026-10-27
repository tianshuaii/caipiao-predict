import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get, type Game } from '../api';
import { loadResearch, saveResearch, removeResearch, parseConstraints, type ResearchConfig, type ResearchResult, type SavedResearch, type ZoneConstraints } from '../research';
import { Balls } from './Balls';

type Draft = Record<string,string>;
const fields=[['odd','奇数个数'],['small','小号个数'],['thirds','三区数量（如 2,2,1）'],['fourths','四区数量（如 1,2,1,1）'],['sum_min','和值下限'],['sum_max','和值上限'],['span_min','跨度下限'],['span_max','跨度上限']];
function draft(value: ZoneConstraints): Draft { return Object.fromEntries(Object.entries(value).filter(([,v])=>v!=null).map(([k,v])=>[k,Array.isArray(v)?v.join(','):String(v)])); }

export function ResearchPanel({game}:{game:Game}) {
  const [front,setFront]=useState<Draft>({});const [back,setBack]=useState<Draft>({});
  const [seed,setSeed]=useState('42');const [count,setCount]=useState('5');const [pool,setPool]=useState('2000');
  const [result,setResult]=useState<ResearchResult|null>(null);const [saved,setSaved]=useState<SavedResearch[]>([]);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [notice,setNotice]=useState('');
  useEffect(()=>{try{setSaved(loadResearch(localStorage));}catch(e){setError(e instanceof Error?e.message:String(e));}},[]);
  function changed(){setResult(null);setNotice('');}
  async function run(event:React.FormEvent) {
    event.preventDefault();setError('');setNotice('');setResult(null);
    try {
      if (![seed,count,pool].every(v=>/^\d+$/.test(v))) throw Error('种子、注数和候选上限必须是整数。');
      const config:ResearchConfig={game,seed:Number(seed),count:Number(count),pool_size:Number(pool),front:parseConstraints(front),back:parseConstraints(back)};
      setBusy(true);setResult(await get<ResearchResult>('/research/selection?config='+encodeURIComponent(JSON.stringify(config))));
    } catch(e){setError(e instanceof Error?e.message:String(e));} finally {setBusy(false);}
  }
  function save(){if(!result)return;try{setSaved(saveResearch(localStorage,result));setNotice('已保存在当前浏览器（最多20条）。');}catch(e){setError(e instanceof Error?e.message:'保存失败');}}
  function load(record:SavedResearch){const c=record.result.config;setFront(draft(c.front));setBack(draft(c.back));setSeed(String(c.seed));setCount(String(c.count));setPool(String(c.pool_size));setResult(record.result);setError('');setNotice('已载入保存的配置与结果，可重新计算。');}
  return <section className="research-panel">
    <div className="research-intro"><h2>约束选号研究</h2><p>按号码结构筛选均匀候选，仅用于模拟。不会改变每天每彩种5注正式建议，也不参与策略评分。</p><p>留空表示不限。小号为≤{game==='ssq'?'16（红球）/8（蓝球）':'17（前区）/6（后区）'}；三区/四区按号码范围等分取整，数量之和须等于本区选球数。</p></div>
    <form onSubmit={run}>
      <fieldset disabled={busy} className="research-settings"><legend>研究设置</legend>
        <label>随机种子<input type="number" min="0" max="2147483647" required value={seed} onChange={e=>{changed();setSeed(e.target.value);}} /></label>
        <label>研究注数（1–10）<input type="number" min="1" max="10" required value={count} onChange={e=>{changed();setCount(e.target.value);}} /></label>
        <label>候选上限（最多2000）<input type="number" min="1" max="2000" required value={pool} onChange={e=>{changed();setPool(e.target.value);}} /></label>
      </fieldset>
      <div className="research-zones">{(['front','back'] as const).map(zone=><fieldset disabled={busy} key={zone}><legend>{zone==='front'?(game==='ssq'?'红球 · 选6个':'前区 · 选5个'):(game==='ssq'?'蓝球 · 选1个':'后区 · 选2个')}</legend><div className="research-fields">{fields.filter(([key])=>!(game==='ssq'&&zone==='back'&&key.startsWith('span'))).map(([key,label])=><label key={key}>{label}<input aria-label={`${zone==='front'?'前区':'后区'}${label}`} type={key==='thirds'||key==='fourths'?'text':'number'} min="0" step="1" placeholder="不限" value={(zone==='front'?front:back)[key]??''} onChange={e=>{changed();(zone==='front'?setFront:setBack)(old=>({...old,[key]:e.target.value}));}} /></label>)}</div></fieldset>)}</div>
      <div className="research-actions"><strong>模拟预算：{Number.isInteger(Number(count))&&Number(count)>=1&&Number(count)<=10?`${Number(count)*2} 元`:'—'}（每注2元，不实际购买）</strong><Button type="submit" isDisabled={busy}>{busy?'筛选中…':'生成研究票组'}</Button></div>
    </form>
    {error&&<p role="alert" className="error-banner">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {result&&<div className="research-result" aria-live="polite"><h3>{result.status==='complete'?'研究结果':result.status==='infeasible'?'约束无解':'已达到搜索上限'}</h3><p>{result.message}</p><p>种子 {result.config.seed} · 尝试 {result.attempts} 次 · 匹配 {result.matched_count} 注 · 计划预算 {result.budget} 元</p>{result.tickets.map((ticket,i)=><Balls key={i} ticket={ticket} />)}<Button onPress={save} isDisabled={busy}>保存配置与结果到本浏览器</Button></div>}
    <div className="research-saved"><h3>本浏览器的研究记录</h3><p>最多保留最近20条，不跨设备同步；清除浏览器数据会丢失记录。</p>{saved.filter(r=>r.result.config.game===game).map(record=><div className="research-saved-row" key={record.id}><span>{new Date(record.created_at).toLocaleString()} · 种子 {record.result.config.seed} · {record.result.config.count} 注</span><Button isDisabled={busy} onPress={()=>load(record)}>载入</Button><Button isDisabled={busy} onPress={()=>{try{setSaved(removeResearch(localStorage,record.id));}catch(e){setError(e instanceof Error?e.message:'删除失败');}}}>删除</Button></div>)}</div>
  </section>;
}
