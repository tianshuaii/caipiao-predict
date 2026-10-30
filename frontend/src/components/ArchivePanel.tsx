import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get, type DataQuality, type Draw, type Game } from '../api';
import { DrawTable } from './DrawTable';

const initial={issue_from:'',issue_to:'',date_from:'',date_to:'',conflict:''};
const time=(value: string | null)=>value ? new Date(value).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}) : '尚无观测';

export function ArchivePanel({ game, revision }: { game: Game; revision: number }) {
  const [draft,setDraft]=useState(initial);
  const [query,setQuery]=useState(initial);
  const [offset,setOffset]=useState(0);
  const [data,setData]=useState<{items:Draw[];total:number} | null>(null);
  const [quality,setQuality]=useState<DataQuality | null>(null);
  const [error,setError]=useState('');
  const [qualityError,setQualityError]=useState('');
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('');
    const params=new URLSearchParams({game,offset:String(offset),limit:'20'});
    Object.entries(query).forEach(([key,value])=>{if(value)params.set(key,value);});
    get<{items:Draw[];total:number}>(`/draws?${params}`,controller.signal)
      .then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(err=>{if(!controller.signal.aborted)setError(String(err));});
    return ()=>controller.abort();
  },[game,query,offset,revision,attempt]);
  useEffect(()=>{
    const controller=new AbortController();setQuality(null);setQualityError('');
    get<DataQuality>(`/data-quality?game=${game}`,controller.signal)
      .then(value=>{if(!controller.signal.aborted)setQuality(value);})
      .catch(err=>{if(!controller.signal.aborted)setQualityError(String(err));});
    return ()=>controller.abort();
  },[game,revision,attempt]);
  const apply=()=>{setOffset(0);setQuery({...draft});};
  return <>
    <section className="panel archive-panel">
      <h2>数据质量 · 当前彩种全库</h2><p>以下汇总不随查询条件变化，缺失列表最多展示100个期号。</p>
      {qualityError && <p role="alert">{qualityError}</p>}{!quality && !qualityError && <p>正在读取质量汇总…</p>}
      {quality && <>
        <div className="archive-quality"><p>已保存 <strong>{quality.count}</strong> 期<br />{quality.first_issue ?? '—'} ～ {quality.last_issue ?? '—'}</p>
          <p>覆盖状态：{quality.complete ? '已核验完整' : '尚未确认完整'}<br />官方清单核验：{quality.inventory_verified ? '已完成' : '未完成'}</p>
          <p>来源冲突 <strong>{quality.conflicts}</strong> 期<br />缺失计数 {quality.missing_count}（含整年缺失项）</p>
          <p>奖金完整 {quality.prize_complete_count} 期<br />不完整 {quality.count-quality.prize_complete_count} 期，未知金额不填零</p></div>
        <p>最新保存的开奖日期：{quality.latest_draw_date ?? '暂无'}；最近新增观测：{time(quality.last_observed_at)}。</p>
        <p>{quality.observation_age_seconds == null ? '暂无可计算的数据时效。' : `距最近新增观测约 ${(quality.observation_age_seconds/3600).toFixed(1)} 小时。`}观测时间不是抓取心跳，也不能单独判定最新应开奖期是否缺失。</p>
        <details><summary>缺失及覆盖说明</summary><p>缺失年份：{quality.missing_years?.join('、') || '无已识别缺年'}</p><p>缺失期号：{quality.missing.join('、') || '无已识别缺期'}</p><p>没有识别出缺口不等于已核验完整；以覆盖状态为准。</p></details>
      </>}
    </section>
    <section className="panel archive-panel">
      <h2>历史开奖查询</h2>
      <form onSubmit={e=>{e.preventDefault();apply();}} className="archive-filters">
        {(['issue_from','issue_to','date_from','date_to'] as const).map(key=><label key={key}>{({issue_from:'起始期号',issue_to:'结束期号',date_from:'起始开奖日期',date_to:'结束开奖日期'})[key]}
          <input type={key.startsWith('date')?'date':'text'} inputMode={key.startsWith('issue')?'numeric':undefined} pattern={key.startsWith('issue')?'[0-9]{7}':undefined} placeholder={key.startsWith('issue')?'如 2026121':undefined} value={draft[key]} onChange={e=>setDraft({...draft,[key]:e.target.value})} /></label>)}
        <label>冲突状态<select value={draft.conflict} onChange={e=>setDraft({...draft,conflict:e.target.value})}><option value="">全部</option><option value="true">有冲突</option><option value="false">无冲突</option></select></label>
        <div className="archive-actions"><Button type="submit">查询</Button><Button type="button" onPress={()=>{setDraft(initial);setQuery(initial);setOffset(0);}}>重置</Button><Button type="button" onPress={()=>setAttempt(v=>v+1)}>重新加载</Button></div>
      </form>
      <p>期号和日期均包含起止边界；全部条件同时满足才显示。展开每期详情可查看奖金、来源观测及修订。</p>
      {error && <p role="alert">{error}</p>}{!data && !error && <p role="status">正在查询…</p>}
      {data && <>{data.items.length ? <DrawTable rows={data.items} history /> : <div className="empty">没有符合条件的开奖记录，请调整筛选条件。</div>}
        <div className="pagination"><span>{data.total===0 ? '共0条' : `第 ${data.items.length ? offset+1 : 0}–${data.items.length ? offset+data.items.length : 0} 条 / 共 ${data.total} 条`}</span><div>
          <Button isDisabled={offset===0} onPress={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button>
          <Button isDisabled={offset+20>=data.total} onPress={()=>setOffset(v=>v+20)}>下一页</Button>
        </div></div></>}
    </section>
  </>;
}
