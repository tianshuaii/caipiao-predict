import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { get, type FeatureAnalysis, type FeatureCatalog, type Game } from '../api';

const percent=(v:number|null)=>v==null?'—':`${(v*100).toFixed(2)}%`;
const value=(v:number|number[]|null|undefined)=>v==null?'不适用 / 无样本':Array.isArray(v)?v.join(' : '):v;

export function AnalysisPanel({game,latestIssue}:{game:Game;latestIssue:string|null}) {
  const [window,setWindow]=useState('20');const [zone,setZone]=useState('front');
  const [draft,setDraft]=useState('');const [cutoff,setCutoff]=useState('');
  const [stamp,setStamp]=useState(()=>new Date().toISOString());
  const [snapshotIssue,setSnapshotIssue]=useState(latestIssue);
  const [data,setData]=useState<FeatureAnalysis|null>(null);const [catalog,setCatalog]=useState<FeatureCatalog|null>(null);
  const [error,setError]=useState('');const [catalogError,setCatalogError]=useState('');
  const [distribution,setDistribution]=useState('sum');const [offset,setOffset]=useState(0);
  const issue=cutoff || snapshotIssue;
  useEffect(()=>{
    const controller=new AbortController();
    get<FeatureCatalog>('/features/catalog',controller.signal).then(v=>{if(!controller.signal.aborted)setCatalog(v);})
      .catch(e=>{if(!controller.signal.aborted)setCatalogError(String(e));});
    return ()=>controller.abort();
  },[]);
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('');setOffset(0);
    if(!issue)return ()=>controller.abort();
    const params=new URLSearchParams({game,zone,window,cutoff_issue:issue,as_of:stamp});
    async function load(){
      const response=await fetch('/api/features?'+params,{signal:controller.signal});
      const body=await response.json();
      if(!response.ok){
        const detail=body.detail;
        throw Error(typeof detail==='string'?detail:detail?.message ? `${detail.message} 冲突 ${detail.conflicts}，缺少观测 ${detail.unavailable_count}。`:'无法计算，请检查截止期或稍后重试。');
      }
      if(!controller.signal.aborted)setData(body);
    }
    load().catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return ()=>controller.abort();
  },[game,zone,window,issue,stamp]);
  return <section className="panel analysis-panel">
    <h2>号码分析 · 历史描述</h2><p>热号、冷号和遗漏反映已保留的数据，不代表下期更容易或更难开出。</p>
    <div className="analysis-controls">
      <label>统计窗口<select value={window} onChange={e=>setWindow(e.target.value)}>{[10,20,30,50,100,500,'all'].map(w=><option key={w} value={w}>{w==='all'?'全部保留记录':`最近${w}条记录`}</option>)}</select></label>
      <label>号码区<select value={zone} onChange={e=>setZone(e.target.value)}><option value="front">{game==='ssq'?'红球':'前区'}</option><option value="back">{game==='ssq'?'蓝球':'后区'}</option></select></label>
      <form onSubmit={e=>{e.preventDefault();setCutoff(draft);}}><label>截止期号（含本期）<input pattern="[0-9]{7}" inputMode="numeric" placeholder={snapshotIssue || '七位期号'} value={draft} onChange={e=>setDraft(e.target.value)} /></label><Button type="submit">应用</Button><Button type="button" onPress={()=>{setDraft('');setCutoff('');}}>最新</Button></form>
      <Button onPress={()=>{setSnapshotIssue(latestIssue);setStamp(new Date().toISOString());}}>刷新观测时点</Button>
    </div>
    <p>观测截止：{new Date(stamp).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}（北京时间，仅本页按钮或重新进入页面更新）；期号截止：{issue ?? '暂无'}。</p>
    {!issue && <p>暂无开奖档案，请先完成数据采集。</p>}{error && <p role="alert">{error}</p>}{issue && !data && !error && <p role="status">正在计算保留快照…</p>}
    {data && <>
      <p>有效 {data.sample_size} 条 / 截止范围可用 {data.available_records} 条；{data.first_issue ?? '—'} ～ {data.last_issue ?? '—'}。{data.short_window && '记录不足所选窗口。'}</p>
      {data.notes.map(note=><p key={note}>{note}</p>)}
      {!data.sample_size ? <p>此快照没有有效记录，不绘制经验频率；理论分布仍可查看。</p> : <>
        <h3>号码频率与均匀基线</h3><p>虚线为每期理论入选概率 {percent(data.theory.number_probability)}；纵轴为保留记录中的出现比例。</p>
        <div className="analysis-chart"><ResponsiveContainer width="100%" height={250}><BarChart data={data.numbers}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="number" /><YAxis tickFormatter={percent} /><Tooltip formatter={v=>percent(Number(v))} /><Bar dataKey="frequency" name="经验频率" fill="#7771ee" /><ReferenceLine y={data.theory.number_probability} stroke="#ad653a" strokeDasharray="5 4" /></BarChart></ResponsiveContainer></div>
      </>}
      <h3>当前遗漏热力图</h3><p>颜色越深表示当前遗漏记录越多；≥ 表示窗口内未出现，只知道下界。它不是“该出了”的信号。</p>
      <div className="omission-grid">{data.numbers.map(n=><div key={n.number} className="omission-cell" style={{background:`rgba(119,113,238,${n.current_omission==null?.04:.08+.4*n.current_omission/Math.max(1,data.sample_size)})`}}>
        <strong>{String(n.number).padStart(2,'0')}</strong><span>{n.current_omission==null?'—':`${n.left_censored?'≥':''}${n.current_omission}`}</span><small>出现 {n.count} 次</small>
      </div>)}</div>
      <details><summary>号码遗漏与排名明细</summary><div className="table-scroll"><table className="experiment-table"><thead><tr><th>号码</th><th>频率</th><th>当前遗漏</th><th>最大 / 平均完成遗漏</th><th>完成间隔数</th><th>热 / 冷排名</th></tr></thead><tbody>{data.numbers.map(n=><tr key={n.number}><td>{n.number}</td><td>{percent(n.frequency)}</td><td>{n.current_omission==null?'—':`${n.left_censored?'≥':''}${n.current_omission}`}</td><td>{value(n.max_omission)} / {n.mean_omission?.toFixed(2) ?? '无完成间隔'}</td><td>{n.completed_intervals}</td><td>{n.hot_rank ?? '—'} / {n.cold_rank ?? '—'}</td></tr>)}</tbody></table></div></details>
      <h3>组合分布与理论对照</h3><label>分布指标 <select value={distribution} onChange={e=>setDistribution(e.target.value)}><option value="sum">和值</option><option value="odd">奇数数量</option><option value="small">小号数量</option></select></label>
      <p>{data.theory.assumption}</p>
      <div className="analysis-chart"><ResponsiveContainer width="100%" height={270}><LineChart data={data.distributions[distribution]}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="value" /><YAxis tickFormatter={percent} /><Tooltip formatter={(v,name)=>[percent(Number(v)),name]} /><Line type="linear" dataKey="frequency" name="经验比例" stroke="#7771ee" dot={false} connectNulls={false} /><Line type="linear" dataKey="theoretical_probability" name="理论概率" stroke="#ad653a" strokeDasharray="5 4" dot={false} /></LineChart></ResponsiveContainer></div>
      <p>实线：经验比例；虚线：理论概率。曲线差异仅供描述，不构成显著性检验或预测优势。</p>
      <details><summary>逐期组合特征（每页20条，按期号升序）</summary><div className="table-scroll"><table className="experiment-table"><thead><tr><th>期号</th><th>和值</th><th>奇偶比</th><th>大小比</th><th>三区比</th><th>跨度 / AC</th><th>与上一保留记录重号</th></tr></thead><tbody>{data.combinations.slice(offset,offset+20).map(c=><tr key={c.issue}><td>{c.issue}</td><td>{value(c.features.sum)}</td><td>{value(c.features.odd_even)}</td><td>{value(c.features.small_big)}</td><td>{value(c.features.thirds)}</td><td>{value(c.features.span)} / {value(c.features.ac)}</td><td>{value(c.features.previous_repeat)}</td></tr>)}</tbody></table></div><div className="analysis-controls"><Button isDisabled={offset===0} onPress={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><span>{data.combinations.length ? offset+1:0}–{Math.min(offset+20,data.combinations.length)} / {data.combinations.length}</span><Button isDisabled={offset+20>=data.combinations.length} onPress={()=>setOffset(v=>v+20)}>下一页</Button></div></details>
      <details><summary>快照溯源</summary><p>版本 {data.version} · 观测时点 {data.as_of} · 截止期 {data.cutoff_issue}</p><p>号码快照 SHA256：{data.dataset_hash}</p></details>
    </>}
    <details><summary>指标定义与空值含义</summary>{catalogError && <p role="alert">{catalogError}</p>}{catalog && <><p>{catalog.version} · {catalog.note}</p>{catalog.features.map(f=><p key={f.id}><strong>{f.id}</strong>：{f.formula}<br />{f.null_semantics}</p>)}</>}</details>
  </section>;
}
