import { useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { get, type Game, type WinnerCases } from '../api';

const types: Record<string,string> = { all:'全部票型', single:'单式', multiple:'复式', banker:'胆拖', mixed:'混合 / 套餐', unknown:'未披露 / 待核对' };
const shown = (value: number | string | null, suffix = '') => value == null ? '未披露' : `${value}${suffix}`;

export function WinnerCasesPanel({ game, revision }: { game: Game; revision: number }) {
  const [type,setType]=useState('all');
  const [offset,setOffset]=useState(0);
  const [data,setData]=useState<WinnerCases | null>(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setError('');setData(null);
    get<WinnerCases>(`/winner-cases?game=${game}&ticket_type=${type}&offset=${offset}`,controller.signal)
      .then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return ()=>controller.abort();
  },[game,type,offset,revision]);
  return <section className="panel">
    <div className="panel-heading"><div><h2>一等奖中奖彩票 · 公开案例</h2><p>阅读官方报道中的票型、投入与中奖结果。</p></div>
      <label>票型筛选 <select aria-label="票型筛选" value={type} onChange={e=>{setType(e.target.value);setOffset(0);}}>{Object.entries(types).map(([v,label])=><option value={v} key={v}>{label}</option>)}</select></label>
    </div>
    <p>{data?.notice || '公开报道样本不完整，同票可能重复报道；不能用中奖案例占比推断哪种票型更容易中奖。'}</p>
    <p>字段由报道文字保守抽取，未经人工核验；“未披露”不代表没有。图片仅提供原文链接，未进行图片识别。此模块不参与选号与策略切换。</p>
    {loading && <p role="status">正在读取案例…</p>}{error && <p role="alert">{error}</p>}
    {data && !data.items.length && <p>暂无符合条件的公开案例。</p>}
    {data?.items.map(c=><article className="provenance" key={c.id}>
      <h3>第 {c.issue} 期 · {types[c.ticket_type]}</h3>
      <p><a href={c.article_url} target="_blank" rel="noopener noreferrer">{c.title} ↗</a> · {c.source} · 发布 {c.published_date || '日期未识别'}</p>
      <p>{c.status==='needs_review' ? '信息存在歧义，需人工核对' : '报道文字已抽取，未经人工核验'}</p>
      <div className="table-scroll"><table className="experiment-table"><thead><tr><th>单式注数</th><th>倍数</th><th>复式选号数</th><th>展开基本组合（不含倍投）</th><th>票面投入</th><th>一等奖注数</th></tr></thead><tbody><tr>
        <td>{shown(c.details.single_count,'注')}</td><td>{shown(c.details.multiplier,'倍')}</td><td>{c.details.front_count && c.details.back_count ? `${c.details.front_count}+${c.details.back_count}` : '未披露 / 不适用'}</td><td>{shown(c.details.expanded_units,'个')}</td><td>{shown(c.details.cost,'元')}</td><td>{shown(c.details.first_prize_count,'注')}</td>
      </tr></tbody></table></div>
      <p>追加：{c.details.additional==null?'未披露 / 不适用':c.details.additional?'是':'否'} · 报道总奖金：{shown(c.details.total_prize_text)}</p>
      <details><summary>查看原文证据与溯源</summary><blockquote>{c.evidence}</blockquote>
        {c.details.banker_description && <p>胆拖细节以以上原文为准，未从中奖号码反推胆码或拖码。</p>}
        <p>抓取时间：{new Date(c.fetched_at).toLocaleString('zh-CN')} · 原始记录 #{c.raw_id} · {c.parser_version}</p>
        {c.images.length>0 && <p>报道附图（不保证每张均为票面）：{c.images.map((url,i)=><a key={url} href={url} target="_blank" rel="noopener noreferrer"> 图片{i+1} </a>)}</p>}
      </details>
    </article>)}
    {data && <div className="pagination"><span>共 {data.total} 条报道案例（非独立中奖票总数）</span><div><Button isDisabled={loading || offset===0} onPress={()=>setOffset(v=>Math.max(0,v-20))}>上一页</Button><Button isDisabled={loading || offset+20>=data.total} onPress={()=>setOffset(v=>v+20)}>下一页</Button></div></div>}
  </section>;
}
