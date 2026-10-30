import { useEffect, useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, BarChart, Bar } from 'recharts';
import { get } from '../api';

type Group = { rule_version:string; issues:string[]; money_issues:string[]; excluded:unknown[]; money_excluded:unknown[];
  series:{strategy:string;max_drawdown_amount:string|null;max_drawdown_ratio:number|null;complete:boolean}[];
  chart:{issue:string;model_equity:string|null;uniform_equity:string|null;model_net:string|null;uniform_net:string|null;model_drawdown:string|null;uniform_drawdown:string|null}[];
  prizes:{level:string;model:number;uniform:number}[]; note:string };
type Projection={available:boolean;strategies:string[];strategy?:string;groups:Group[];note:string};
export function BacktestCharts({source,id}:{source:'experiment'|'job';id:number}){
  const [strategy,setStrategy]=useState('');const [metric,setMetric]=useState('equity');
  const [data,setData]=useState<Projection|null>(null);const [error,setError]=useState('');
  useEffect(()=>{const c=new AbortController();setData(null);setError('');
    get<Projection>(`/visualizations?source=${source}&id=${id}&strategy=${encodeURIComponent(strategy)}`,c.signal)
      .then(v=>{if(!c.signal.aborted)setData(v);}).catch(e=>{if(!c.signal.aborted)setError(String(e));});
    return()=>c.abort();},[source,id,strategy]);
  return <section className="archive-panel"><h3>回测资金与奖级图</h3>{error && <p role="alert">{error}</p>}
    {!data && !error && <p>读取已保存的逐期结果…</p>}
    {data && <><p>{data.note}</p>{data.strategies.length>0 && <label>策略<select value={data.strategy} onChange={e=>setStrategy(e.target.value)}>{data.strategies.map(s=><option key={s}>{s}</option>)}</select></label>}
    {!data.available && <p>没有可比较的逐期数据。</p>}
    <label>曲线<select value={metric} onChange={e=>setMetric(e.target.value)}><option value="equity">账面资金（初始1000元）</option><option value="net">累计净收益</option><option value="drawdown">期末回撤金额</option></select></label>
    {data.groups.map(g=><div key={g.rule_version}><h4>规则 {g.rule_version} · 共同 {g.issues.length} 期 · 奖金完整 {g.money_issues.length} 期</h4>
      <p>排除 {g.excluded.length} 期；未知奖金 {g.money_excluded.length} 期。横轴为有效共同期次，不代表连续日历期。</p>
      {g.chart.length>0 && <ResponsiveContainer width="100%" height={280}><LineChart data={g.chart.map(p=>({...p,model:p[`model_${metric}` as keyof typeof p]==null?null:Number(p[`model_${metric}` as keyof typeof p]),uniform:p[`uniform_${metric}` as keyof typeof p]==null?null:Number(p[`uniform_${metric}` as keyof typeof p])}))}><XAxis dataKey="issue"/><YAxis/><Tooltip/><Legend/><Line dataKey="model" name={data.strategy} stroke="#7357d8" connectNulls={false}/><Line dataKey="uniform" name="单一随机基线" stroke="#159a8c" connectNulls={false}/></LineChart></ResponsiveContainer>}
      {g.series.map(s=><p key={s.strategy}>{s.strategy}：最大回撤 {s.max_drawdown_amount==null?'不可估计':`¥${s.max_drawdown_amount}`} / {s.max_drawdown_ratio==null?'不可估计':`${(s.max_drawdown_ratio*100).toFixed(2)}%`}{!s.complete?'（双方共同金额边界不完整）':''}</p>)}
      <p>{g.note}</p><h4>各奖级中奖注数</h4>{g.prizes.length?<ResponsiveContainer width="100%" height={220}><BarChart data={g.prizes}><XAxis dataKey="level"/><YAxis allowDecimals={false}/><Tooltip/><Legend/><Bar dataKey="model" name={data.strategy} fill="#7357d8"/><Bar dataKey="uniform" name="单一随机基线" fill="#159a8c"/></BarChart></ResponsiveContainer>:<p>共同期次内暂无中奖注。</p>}
      <details><summary>查看图表原值、排除原因及完整统计</summary><pre className="model-json">{JSON.stringify(g,null,2)}</pre></details>
    </div>)}</>}
  </section>;
}
