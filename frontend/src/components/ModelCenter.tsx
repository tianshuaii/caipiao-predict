import { BacktestCharts } from './BacktestCharts';
import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get, type Game, type ResearchJob, type ResearchJobConfig, type ResearchModelCatalog } from '../api';
import { adminRequest } from '../auth';
import { strategyName } from '../strategies';

const states:Record<string,string>={queued:'排队中',running:'运行中',succeeded:'已完成',failed:'失败'};
const date=(s:string|null)=>s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—';
export function ModelCenter({game,latestIssue,adminName}:{game:Game;latestIssue:string|null;adminName?:string}){
  const [config,setConfig]=useState<ResearchJobConfig>({game,kind:'backtest',model:'frequency',window:300,periods:5,budget:50,seed:20261023,issue_to:latestIssue || ''});
  const [catalog,setCatalog]=useState<ResearchModelCatalog|null>(null);
  const [jobs,setJobs]=useState<ResearchJob[]>([]);const [total,setTotal]=useState(0);const [offset,setOffset]=useState(0);
  const [selected,setSelected]=useState<number|null>(null);const [detail,setDetail]=useState<ResearchJob|null>(null);
  const [error,setError]=useState('');const [submitError,setSubmitError]=useState('');const [detailError,setDetailError]=useState('');const [busy,setBusy]=useState(false);const [tick,setTick]=useState(0);
  useEffect(()=>{const timer=setInterval(()=>setTick(v=>v+1),10000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{
    const controller=new AbortController();setError('');
    Promise.all([get<ResearchModelCatalog>('/research/models',controller.signal),get<{items:ResearchJob[];total:number}>(`/research/jobs?limit=20&offset=${offset}`,controller.signal)])
      .then(([c,j])=>{if(!controller.signal.aborted){setCatalog(c);setJobs(j.items);setTotal(j.total);}})
      .catch(e=>{if(!controller.signal.aborted)setError(String(e));});
    return()=>controller.abort();
  },[tick,offset]);
  useEffect(()=>{setDetail(null);},[selected]);
  useEffect(()=>{
    const controller=new AbortController();setDetailError('');
    if(selected!=null)get<ResearchJob>(`/research/jobs/${selected}`,controller.signal).then(v=>{if(!controller.signal.aborted)setDetail(v);}).catch(e=>{if(!controller.signal.aborted)setDetailError(String(e));});
    return()=>controller.abort();
  },[selected,tick]);
  async function submit(e:React.FormEvent){
    e.preventDefault();setBusy(true);setSubmitError('');
    try{const job=await adminRequest<ResearchJob>('/research/jobs',{method:'POST',body:JSON.stringify(config)});setSelected(job.id);setOffset(0);setTick(v=>v+1);}
    catch(e){setSubmitError(e instanceof Error?e.message:String(e));}
    finally{setBusy(false);}
  }
  return <section className="panel archive-panel">
    <h2>模型中心 · 离线研究任务</h2><p>任务由独立工作进程执行，每次冻结配置及当前修订数据。只有一个待处理或运行槽位，提交不会直接在网页请求中训练。</p>
    {!adminName && <p>当前为公共只读；请通过右上角管理员登录后提交任务。</p>}
    {error && <p role="alert">{error}（已有列表可能是上次读取结果）</p>}
    {catalog && <form onSubmit={submit} className="archive-filters">
      <label>任务类型<select value={config.kind} onChange={e=>setConfig({...config,kind:e.target.value as 'train'|'backtest',periods:e.target.value==='train'?1:5,budget:e.target.value==='train'?10:50})}><option value="train">训练并保存模型</option><option value="backtest">与随机基线滚动回测</option></select></label>
      <label>模型与特征方案<select value={config.model} onChange={e=>setConfig({...config,model:e.target.value})}>{catalog.models.map(m=><option key={m.id} value={m.id}>{strategyName(m.id)} · {m.id}</option>)}</select></label>
      <label>训练窗口<select value={config.window} onChange={e=>setConfig({...config,window:Number(e.target.value)})}>{catalog.windows.map(w=><option key={w} value={w}>{w}条保留记录</option>)}</select></label>
      <label>研究截止期<input required pattern="[0-9]{7}" inputMode="numeric" value={config.issue_to} onChange={e=>setConfig({...config,issue_to:e.target.value})} /></label>
      <label>回测期数<input type="number" min="1" max={catalog.max_periods} disabled={config.kind==='train'} value={config.periods} onChange={e=>setConfig({...config,periods:Number(e.target.value)})} /></label>
      <label>模型模拟预算上限（元）<input type="number" min="10" max={catalog.max_budget} step="10" value={config.budget} onChange={e=>setConfig({...config,budget:Number(e.target.value)})} /></label>
      <label>随机种子<input type="number" min="0" max="4294967295" value={config.seed} onChange={e=>setConfig({...config,seed:Number(e.target.value)})} /></label>
      <Button type="submit" isDisabled={!adminName || busy}>{busy?'提交中…':'提交新研究任务'}</Button>
    </form>}
    <p>特征组：{catalog?.models.find(m=>m.id===config.model)?.features.join('、') || '该模型内置基础特征'}。{config.kind==='train'?'训练需要完整窗口历史，不生成投注建议。':`每期模型和基线各5注：模型计划成本¥${config.periods*10}，随机对照另计同额；需窗口+回测期数的完整记录。`}</p>
    {submitError && <p role="alert">{submitError}</p>}<p>{catalog?.note}</p>
    <h3>研究任务（全部彩种，每10秒刷新）</h3><p>长期排队表示工作进程可能未启动；本页不会自动启动工作进程或触发正式预测。</p>
    {!jobs.length && <p>暂无任务。</p>}
    <div className="table-scroll"><table className="experiment-table"><thead><tr><th>任务</th><th>彩种 / 模型</th><th>状态</th><th>窗口 / 期数</th><th>提交 / 开始 / 完成</th><th>查看</th></tr></thead><tbody>{jobs.map(j=><tr key={j.id}><td>#{j.id} · {j.config.kind}</td><td>{j.config.game} · {strategyName(j.config.model)}</td><td>{states[j.status] || j.status}<small>{j.error}</small></td><td>{j.config.window} / {j.config.periods}</td><td>{date(j.created_at)}<small>{date(j.started_at)} / {date(j.finished_at)}</small></td><td><Button onPress={()=>setSelected(j.id)}>详情</Button></td></tr>)}</tbody></table></div>
    <div className="pagination"><span>共{total}项</span><div><Button isDisabled={offset===0} onPress={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><Button isDisabled={offset+20>=total} onPress={()=>setOffset(v=>v+20)}>下一页</Button></div></div>
    {detailError && <p role="alert">{detailError}</p>}
    {detail && <div><h3>任务 #{detail.id} · {states[detail.status]}</h3>{detail.status==='succeeded' && detail.config.kind==='backtest' && <BacktestCharts key={detail.id} source="job" id={detail.id}/>}<p>运行耗时：{detail.duration_seconds==null?'尚未开始':`${detail.duration_seconds.toFixed(1)}秒`}</p><p>快照 SHA256：{detail.snapshot_hash}</p><p>提交时模型配方：{detail.recipe_hash}</p><p>{detail.error}</p><details><summary>冻结配置</summary><pre className="model-json">{JSON.stringify(detail.config,null,2)}</pre></details><details><summary>研究结果、模型元数据与产物ID</summary><pre className="model-json">{detail.result?JSON.stringify(detail.result,null,2):'尚无结果'}</pre></details></div>}
  </section>;
}
