import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get, type Game } from '../api';
type ExportData={report:{sha256:string;data:{version:string;generated_at:string;game:string;cutoff:{issue:string|null;draw_date:string|null;evaluation_issue:string|null};quality:{count:number;missing_count:number;conflicts:number;complete:boolean};statistics:{status:string};limitations:string[]}};json:string;markdown:string};
export function ExportPanel({game}:{game:Game}){
  const [value,setValue]=useState<ExportData|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [revision,setRevision]=useState(0);
  useEffect(()=>{const c=new AbortController();setBusy(true);setValue(null);setError('');
    get<ExportData>(`/research/export?game=${game}`,c.signal).then(v=>{if(!c.signal.aborted)setValue(v);}).catch(e=>{if(!c.signal.aborted)setError(String(e));}).finally(()=>{if(!c.signal.aborted)setBusy(false);});return()=>c.abort();},[game,revision]);
  function download(kind:'json'|'markdown'){
    if(!value)return;const blob=new Blob([value[kind]],{type:kind==='json'?'application/json;charset=utf-8':'text/markdown;charset=utf-8'});
    const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`lottery-${game}-${value.report.sha256.slice(0,12)}.${kind==='json'?'json':'md'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  return <section className="panel archive-panel"><h2>研究报表与导出</h2><p>导出当前读取的完整研究指标，不采集、不训练、不推送。下载的JSON与Markdown共享同一份内容；重新读取才更新报表。</p><Button isDisabled={busy} onPress={()=>setRevision(v=>v+1)}>{busy?'正在整理…':'重新读取'}</Button>{error&&<p role="alert">{error}</p>}
    {value&&<><p>{value.report.data.version} · 生成于 {new Date(value.report.data.generated_at).toLocaleString()}</p><p>开奖截止 {value.report.data.cutoff.issue??'暂无'} · {value.report.data.cutoff.draw_date??'暂无'}；评估目标期截止 {value.report.data.cutoff.evaluation_issue??'暂无'}（可能尚未开奖）。</p><p>历史 {value.report.data.quality.count} 期，缺失 {value.report.data.quality.missing_count}，冲突 {value.report.data.quality.conflicts}。统计检验：{value.report.data.statistics.status==='available'?'已附原报告':'尚无可用报告'}。</p><p>内容SHA256：{value.report.sha256}</p><Button onPress={()=>download('json')}>下载完整JSON</Button><Button onPress={()=>download('markdown')}>下载Markdown</Button><ul>{value.report.data.limitations.map(s=><li key={s}>{s}</li>)}</ul><details><summary>报表预览（含所有指标原值）</summary><pre className="model-json">{value.markdown}</pre></details></>}
  </section>;
}
