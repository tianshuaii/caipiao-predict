import { useEffect, useState } from 'react';
import { get, type Game, type RankingObjective, type RankingStatus, type StatisticalInterval } from '../api';
import { strategyName } from '../strategies';

const reasons: Record<string,string> = {
  insufficient_periods:'共同样本少于30期，暂不排名', no_first_prize_observed:'共同样本尚无一等奖，无法区分',
  common_periods_equal_budget:'按共同期次、相同预算排序；相同值并列', generation_failed:'生成失败',
  invalid_forecast_cutoff:'预测截止时间无效', awaiting_draw:'等待开奖', draw_conflict:'开奖数据冲突',
  missing_current_revision_score:'缺少当前开奖版本评分', budget_mismatch:'不是5注10元的完整评分', invalid_brier:'概率评分无效',
};
const pct = (v: number | null) => v == null ? '—' : `${(v*100).toFixed(2)}%`;
const ci = (v?: StatisticalInterval) => v?.interval ? v.interval.map(pct).join(' ～ ') : '不可估计';

export function RankingPanel({ game, revision }: { game: Game; revision: number }) {
  const [objective,setObjective]=useState<RankingObjective>('brier');
  const [data,setData]=useState<RankingStatus | null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('');
    get<RankingStatus>(`/rankings?game=${game}&objective=${objective}`,controller.signal)
      .then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(err=>{if(!controller.signal.aborted)setError(String(err));});
    return ()=>controller.abort();
  },[game,objective,revision]);
  return <section className="panel">
    <div className="panel-heading"><h2>候选策略排行</h2><label>排序目标 <select aria-label="排行目标" value={objective} onChange={e=>setObjective(e.target.value as RankingObjective)}>
      <option value="brier">Brier（越低越好）</option><option value="any_prize">任意奖比例</option><option value="first_prize">一等奖比例</option><option value="roi">模拟收益 ROI</option>
    </select></label></div>
    <p>只比较当前候选版本的共同有效期次，每期5注、10元。至少30期才显示名次；此门槛与正式策略晋升不同。</p>
    {error && <p role="alert">{error}</p>}{!data && !error && <p>正在加载排行…</p>}
    {data && !data.groups.length && <p>暂无共同评估数据，等待有效开奖评分。</p>}
    {data?.groups.map(group=><div key={group.rule_version}>
      <h3>{group.rule_version} · 共同 {group.issues.length} 期 · 金额完整 {group.money_issues.length} 期</h3>
      <div className="table-scroll"><table className="experiment-table"><thead><tr><th>名次 / 策略</th><th>同期 Brier ↓</th><th>任意奖比例 / 95%区间</th><th>一等奖比例 / 95%区间</th><th>完整金额子集成本 / 净收益 / ROI</th><th>目标样本 / 排序理由</th></tr></thead><tbody>
        {group.rows.map(row=><tr key={row.strategy}>
          <td>{row.rank ?? '—'} · {strategyName(row.strategy)}<small>{row.strategy}</small></td>
          <td>{row.brier?.toFixed(6) ?? '—'}</td>
          <td>{pct(row.metrics.any_prize_rate)}<small>{ci(row.metrics.any_prize_interval)}</small></td>
          <td>{pct(row.metrics.first_prize_rate)}<small>{ci(row.metrics.first_prize_interval)}</small></td>
          <td>¥{row.money_metrics.cost} / {row.money_metrics.net == null ? '—' : `¥${row.money_metrics.net}`} / {pct(row.money_metrics.roi)}</td>
          <td>{row.periods}期<small>{reasons[row.reason] ?? row.reason}</small></td>
        </tr>)}
      </tbody></table></div>
      <details className="provenance"><summary>比较期次与剔除明细</summary>
        <p>共同期号：{group.issues.join('、') || '无'}</p><p>奖金完整期号：{group.money_issues.join('、') || '无'}</p>
        {group.excluded.map(e=><p key={e.issue}>{e.issue}：缺少有效评分 {e.missing_strategies.map(strategyName).join('、')}</p>)}
        {group.money_excluded.map(e=><p key={e.issue}>{e.issue}：至少一个策略奖金待确认，从所有策略收益比较中剔除</p>)}
      </details>
    </div>)}
    {!!data?.excluded.length && <details className="provenance"><summary>未纳入的候选记录（{data.excluded.length}）</summary>{data.excluded.map(e=><p key={`${e.strategy}:${e.issue}`}>{e.issue} · {strategyName(e.strategy)}：{reasons[e.reason] ?? e.reason}</p>)}</details>}
    <p className="experiment-notes">{data?.note}</p>
  </section>;
}
