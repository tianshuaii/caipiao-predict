import type { PortfolioStatus, StatisticalInterval } from '../api';

const percent = (v: number | null) => v == null ? '—' : `${(v * 100).toFixed(2)}%`;
const money = (v: string | number | null) => v == null ? '待结算' : `¥${Number(v).toFixed(2)}`;
const band = (v: number[] | null, cash = false) => v == null ? '暂无同期完整样本' : `${cash ? money(v[1]) : percent(v[1])}（${cash ? money(v[0]) : percent(v[0])} ～ ${cash ? money(v[2]) : percent(v[2])}）`;

const reasons: Record<string,string> = { degenerate_resampling_distribution:'重采样分布退化，无法估计区间', insufficient_periods:'少于30期', constant_observed_difference:'观察差值无变化，不能据此认定无不确定性', short_contiguous_segment:'连续片段不足5期', rare_first_prize_events:'一等奖事件不足5个期次' };
const interval = (v: StatisticalInterval | undefined, cash = false) => !v ? '—' : v.interval ? v.interval.map(x=>cash?money(x):percent(x)).join(' ～ ') : `不可估计${v.reason ? `：${reasons[v.reason] ?? v.reason}` : ''}`;

export function PortfolioPanel({ data }: { data: PortfolioStatus | undefined }) {
  if (!data) return null;
  return <div>
    <h3>整组中奖与模拟收益</h3>
    <p>每期5注作为一组：“任意奖”和“一等奖”均按整组至少命中一注统计。每期提前冻结 {data.control_groups} 组随机对照，各组同样5注、成本10元，不推送、不参与策略晋升。</p>
    {!data.rows.length && <p>等待开奖后的有效评分。不会给已开奖期补造前瞻随机对照。</p>}
    {data.rows.map(row => <details className="provenance" key={`${row.kind}:${row.strategy}:${row.rule_version}`}>
      <summary>{row.kind === 'formal' ? '正式建议' : '候选策略'} · {row.strategy} · {row.rule_version} · {row.metrics.periods}期</summary>
      <div className="table-scroll"><table className="experiment-table"><thead><tr><th>有效期数</th><th>任意奖期数 / 比例</th><th>一等奖期数 / 比例</th><th>模拟成本</th><th>已确认奖金</th><th>净收益 / ROI</th></tr></thead><tbody><tr>
        <td>{row.metrics.periods}</td><td>{row.metrics.any_prize_periods} / {percent(row.metrics.any_prize_rate)}</td><td>{row.metrics.first_prize_periods} / {percent(row.metrics.first_prize_rate)}</td><td>{money(row.metrics.cost)}</td><td>{money(row.metrics.known_return)}{row.metrics.pending_tickets > 0 && <small>{row.metrics.pending_tickets}注待结算</small>}</td><td>{money(row.metrics.net)} / {percent(row.metrics.roi)}</td>
      </tr></tbody></table></div>
      <p>中奖期比例95% Wilson区间：任意奖 {interval(row.metrics.any_prize_interval)}；一等奖 {interval(row.metrics.first_prize_interval)}。独立、固定概率近似下的探索性区间，不代表下期预测。</p>
      <p>同期随机对照：中奖比较 {row.comparison.periods} 期；双方奖金完整的收益比较 {row.comparison.money_periods} 期。以下策略成绩仅使用这些匹配期次。</p>
      <div className="table-scroll"><table className="experiment-table"><thead><tr><th>目标</th><th>策略同期结果</th><th>随机对照中位数（2.5% ～ 97.5%）</th></tr></thead><tbody>
        <tr><td>整组任意奖比例</td><td>{percent(row.comparison.strategy.any_prize_rate)}</td><td>{band(row.comparison.random_any_prize_rate)}</td></tr>
        <tr><td>整组一等奖比例</td><td>{percent(row.comparison.strategy.first_prize_rate)}</td><td>{band(row.comparison.random_first_prize_rate)}</td></tr>
        <tr><td>模拟净收益</td><td>{row.comparison.money_periods ? money(row.comparison.money_strategy.net) : '暂无同期完整样本'}</td><td>{band(row.comparison.random_net, true)}</td></tr>
        <tr><td>模拟ROI</td><td>{percent(row.comparison.money_strategy.roi)}</td><td>{band(row.comparison.random_roi)}</td></tr>
      </tbody></table></div>
      {row.comparison.uncertainty && <div>
        <p>策略减同期100组对照均值 · 95%分块Bootstrap区间：任意奖比例差 {interval(row.comparison.uncertainty.any_prize)}；一等奖比例差 {interval(row.comparison.uncertainty.first_prize)}；每期净收益差 {interval(row.comparison.uncertainty.net_per_period,true)}。</p>
        <p>中奖比较 {row.comparison.uncertainty.any_prize.periods} 期，金额比较 {row.comparison.uncertainty.net_per_period.periods} 期；按 {row.comparison.uncertainty.any_prize.block_length} 期块，配置重采样 {row.comparison.uncertainty.any_prize.replicates} 次（种子 {row.comparison.uncertainty.any_prize.seed}）。{row.comparison.uncertainty.note}</p>
      </div>}
    </details>)}
    <p className="experiment-notes">{data.note} ROI为净收益÷成本；没有中一等奖不代表其真实概率为零。</p>
  </div>;
}
