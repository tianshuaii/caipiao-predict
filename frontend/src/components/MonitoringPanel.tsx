import { useEffect, useState } from 'react';
import { get } from '../api';
type State={monitor_fresh:boolean;checked_at:string|null;checks:Record<string,{healthy:boolean|null;observed:boolean|null}>;events:{id:number;label:string;kind:string;at:string;delivery:string}[]};
const names:Record<string,string>={database:'数据库',disk:'磁盘',scheduler:'调度心跳',nightly:'夜间任务',research:'研究任务',candidates:'候选模型',history_dlt:'大乐透完整性',history_ssq:'双色球完整性',sources:'开奖来源',latest:'最新开奖'};
export function MonitoringPanel(){
  const [state,setState]=useState<State|null>(null);const [error,setError]=useState('');
  useEffect(()=>{const controller=new AbortController();let active=true;
    async function refresh(){try{const value=await get<State>('/monitoring',controller.signal);if(active){setState(value);setError('');}}catch(e){if(active)setError(String(e));}}
    void refresh();const timer=setInterval(refresh,60000);return()=>{active=false;controller.abort();clearInterval(timer);};},[]);
  return <section className="panel archive-panel"><h2>运行监控与告警</h2><p>独立监控进程每60秒检查；与普通晨报分开。默认仅记录，需显式启用推送。状态过期不代表服务健康。</p>{error&&<p role="alert">{error}</p>}{state&&<><p>{state.monitor_fresh?'监控记录新鲜':'监控尚未启动或记录已过期'} · {state.checked_at?new Date(state.checked_at).toLocaleString():'暂无检测'}</p><div className="table-scroll"><table className="experiment-table"><thead><tr><th>检查项</th><th>最近观测</th><th>保留状态</th></tr></thead><tbody>{Object.entries(state.checks).map(([key,v])=><tr key={key}><td>{names[key]||key}</td><td>{v.observed==null?'未知':v.observed?'正常':'异常'}</td><td>{v.healthy==null?'未知':v.healthy?'正常':'异常'}</td></tr>)}</tbody></table></div><h3>故障及恢复事件（最近200条）</h3><div className="table-scroll"><table className="experiment-table"><thead><tr><th>时间</th><th>检查项</th><th>事件</th><th>推送</th></tr></thead><tbody>{[...state.events].reverse().map(e=><tr key={e.id}><td>{new Date(e.at).toLocaleString()}</td><td>{e.label}</td><td>{e.kind==='recovery'?'恢复':'故障'}</td><td>{({disabled:'未启用',sending:'发送中或进程中断，请人工核对',sent:'通道已受理',uncertain:'结果不确定，不自动重发',failed:'发送失败',not_configured:'通道未配置'} as Record<string,string>)[e.delivery]||e.delivery}</td></tr>)}</tbody></table></div></>}</section>;
}
