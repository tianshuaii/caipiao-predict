import { useEffect, useState } from 'react';
import { get, type Draw, type DrawDetails } from '../api';
import { Balls } from './Balls';
import { money, sourceNames } from './DrawTable';

export function DrawObservations({ row }: { row: Draw }) {
  const [data,setData]=useState<DrawDetails | null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('');
    get<DrawDetails>(`/draws/${row.game}/${row.issue}`,controller.signal)
      .then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(err=>{if(!controller.signal.aborted)setError(String(err));});
    return ()=>controller.abort();
  },[row.game,row.issue,row.updated_at]);
  return <div className="archive-observations">
    <h3>来源观测与修订</h3>
    {error && <p role="alert">{error}</p>}{!data && !error && <p>正在读取观测记录…</p>}
    {data && <><p>当前修订版本 {data.revision} · {data.conflict ? '存在来源冲突，待核验' : '当前未标记冲突'} · 更新于 {new Date(data.updated_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}</p>
      {!data.observations.length && <p>尚无留存观测，无法追溯此前变更。</p>}
      {data.observations.map((o,i)=><details key={i}><summary>观测 {i+1} · {sourceNames[o.source] || o.source} · {new Date(o.created_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})} · {o.conflict ? '当时标记冲突' : '当时未标记冲突'}</summary>
        <p>原始响应ID：{o.raw_id ?? '未关联'} · 开奖日期 {o.data.draw_date}</p><Balls ticket={o.data} compact />
        <p>{Object.entries(o.data.prizes).map(([level,prize])=>`${level}等奖：${money(prize.amount)}元 / ${prize.count ?? '未知'}注`).join('；')}</p>
        <a href={o.data.source_url} target="_blank" rel="noreferrer">查看该次来源公告</a>
      </details>)}
      <p>观测顺序不等于官方修订编号；历史冲突标记保留原貌。</p></>}
  </div>;
}
