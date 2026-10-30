import { useState } from 'react';
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';
import type { PortfolioStatus } from '../api';
export function RandomTracks({comparison:c}:{comparison:PortfolioStatus['rows'][number]['comparison']}){
  const [metric,setMetric]=useState<'any_prize_rate'|'first_prize_rate'|'net'|'roi'>('any_prize_rate');
  const cash=metric==='net'||metric==='roi';const tracks=cash?c.random_money_tracks:c.random_tracks;
  const strategy=(cash?c.money_strategy:c.strategy)[metric];const periods=cash?c.money_periods:c.periods;
  const points=(tracks||[]).map((t,i)=>({track:i+1,value:t[metric]==null?null:Number(t[metric])}));
  return <div><h4>前瞻随机轨迹分布与策略位置</h4><label>比较目标<select value={metric} onChange={e=>setMetric(e.target.value as typeof metric)}><option value="any_prize_rate">整组任意奖比例</option><option value="first_prize_rate">整组一等奖比例</option><option value="net">模拟净收益（元）</option><option value="roi">ROI</option></select></label>
    <p>共同 {periods} 期 · {points.length} 组冻结轨迹。比例以0～1表示；横轴为轨迹编号。上表随机2.5%～97.5%分位数描述随机结果范围，不是策略胜率的置信区间。</p>
    {periods>0 && points.length>0?<ResponsiveContainer width="100%" height={260}><ScatterChart><XAxis type="number" dataKey="track" name="轨迹编号"/><YAxis type="number" dataKey="value" domain={['auto','auto']}/><Tooltip/><Scatter name="随机轨迹" data={points.filter(p=>p.value!==null)} fill="#159a8c"/>{strategy!=null && <ReferenceLine y={Number(strategy)} stroke="#7357d8" ifOverflow="extendDomain" label="策略同期结果"/>}</ScatterChart></ResponsiveContainer>:<p>暂无共同有效样本。</p>}
    <details><summary>查看随机轨迹原值</summary><pre className="model-json">{JSON.stringify({metric,periods,strategy,tracks:points},null,2)}</pre></details>
  </div>;
}
