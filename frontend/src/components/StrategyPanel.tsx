import { PortfolioPanel } from './PortfolioPanel';
import { Balls } from './Balls';
import { strategyCatalog, strategyName as name } from '../strategies';
import type { StrategyStatus } from '../api';

const score = (value: number | null) => value == null ? '等待开奖' : value.toFixed(6);

export function StrategyPanel({ data }: { data: StrategyStatus | null }) {
  if (!data) return null;
  return <section className="panel">
    <div className="panel-heading"><div><h2>前瞻验证与自动切换</h2><p>当前正式策略：{name(data.active)} · {data.active}</p></div></div>
    <p>每期开奖前冻结候选预测，开奖后评分。至少 {data.minimum_samples} 期、累计概率评分改善 ≥ {(data.minimum_relative_gain * 100).toFixed(0)}%、最近 30 期更优，并通过持续证据门槛，才允许切换。</p>
    <details className="provenance"><summary>14 种候选策略 · 每种 5 注 · 每彩种共 70 注测试，正式建议仅 5 注</summary><p>新增策略以基础逻辑回归为对照，联合学习指标与频率交互；不强制固定奇偶比例、不假设遗漏越久越容易开出。投注行为指标暂无可靠数据。</p><table className="experiment-table"><thead><tr><th>策略</th><th>使用信息</th></tr></thead><tbody>{Object.entries(strategyCatalog).filter(([key]) => key !== 'uniform').map(([key, value]) => <tr key={key}><td>{value.name}</td><td>{value.features}</td></tr>)}</tbody></table><p>各策略内部去重，跨策略允许重合；70 注是候选总量，不代表70注不同号码或70个独立样本。历史结构特征不等于对整注联合概率建模。新增版本从零积累前瞻证据。</p></details>
    <div className="table-scroll"><table className="experiment-table"><thead><tr><th>候选模型</th><th>前瞻已评分 / 已预测</th><th>Brier ↓</th><th>随机基线 ↓</th><th>改善</th><th>证据值 / 门槛</th><th>状态</th></tr></thead><tbody>
      {data.candidates.filter(c => c.current_version).map(c => <tr key={c.strategy}><td><strong>{name(c.strategy)}</strong><small>{c.strategy}</small></td><td>{c.samples} / {c.forecast_count}</td><td>{score(c.brier)}</td><td>{score(c.baseline)}</td><td>{c.relative_gain == null ? '—' : `${(c.relative_gain * 100).toFixed(2)}%`}</td><td>{c.e_value.toPrecision(3)} / {c.threshold}</td><td>{c.latest_error ? '生成失败，已保护正式预测' : c.eligible ? '达到晋升门槛' : c.samples < data.minimum_samples ? '积累前瞻样本' : '证据尚不足'}{c.failed > 0 && <small>累计失败 {c.failed} 期</small>}</td></tr>)}
    </tbody></table></div>
    {!data.candidates.length && <p>等待下一次任务冻结候选预测；历史回测不会计入这里。</p>}
    <div className="experiment-notes"><p>证据值不是中奖概率。每个新版本单独积累样本并分配检验预算，持续查看不会重置证据；模型退化或运行异常时回退基线。</p><p>当前正式策略仅影响新生成的号码，已冻结的本期预测保持不变。历史回测仅供研究，不直接触发切换。</p></div>
    <PortfolioPanel data={data.portfolio} />
    <h3>各策略号码与逐期评分</h3><p>每组为5注单式；微信只发送每个彩种正式推荐的5注。</p>
    <div className="review-list">{data.forecasts?.map(f => <details className="provenance" key={f.id}><summary>{f.issue} · {name(f.strategy)} · {f.error ? '生成失败' : f.metrics ? `Brier ${f.metrics.brier.toFixed(6)} · 平均命中 ${f.metrics.mean_hits.toFixed(2)}` : '等待开奖评分'}</summary>
      {f.error && <p>{f.error}</p>}{f.tickets.map((ticket,i) => <div className="ticket" key={i}><span className="ticket-index">{i+1}</span><Balls ticket={ticket} compact /><span>{f.metrics ? `${f.metrics.results[i].front_hits}+${f.metrics.results[i].back_hits} · ¥${f.metrics.results[i].amount ?? '待确认'}` : '单式'}</span></div>)}
      {f.metrics && <p>模拟成本 ¥{f.metrics.cost} · 已知奖金 ¥{f.metrics.known_return} · {f.metrics.pending ? `${f.metrics.pending} 注奖金待确认` : `净收益 ¥${(Number(f.metrics.known_return)-f.metrics.cost).toFixed(2)}`}</p>}
    </details>)}</div>
    <h3>策略决策记录</h3><div className="experiment-log">{data.decisions.map(d => <div key={d.id}><div><strong>{name(d.previous)} → {name(d.selected)}</strong><p>{d.reason} · {new Date(d.created_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })}</p></div></div>)}</div>
  </section>;
}
