import { useState } from 'react';
import { Button } from '@heroui/react';
import { ChevronDown, ExternalLink } from 'lucide-react';
import type { Draw } from '../api';
import { Balls } from './Balls';

export function money(value: string | number | null | undefined) {
  return value == null ? '待公布' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}
export const sourceNames: Record<string, string> = { cwl: '中国福彩网', sporttery: '中国体育彩票', shanghai: '上海福彩', zhcw: '中彩网 · 福彩指定媒体' };

export function DrawTable({ rows }: { rows: Draw[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!rows.length) return <div className="empty">暂无开奖记录，等待官方数据同步。</div>;
  return <div className="table-scroll"><table className="draw-table"><thead><tr><th>期号 / 开奖日期</th><th>开奖号码</th><th>一等奖单注奖金</th><th>数据来源</th><th><span className="sr-only">详情</span></th></tr></thead><tbody>
    {rows.map(row => <DrawRows key={row.issue} row={row} expanded={expanded === row.issue} toggle={() => setExpanded(expanded === row.issue ? null : row.issue)} />)}
  </tbody></table></div>;
}

function DrawRows({ row, expanded, toggle }: { row: Draw; expanded: boolean; toggle: () => void }) {
  return <><tr><td><strong>{row.issue}</strong><small>{row.draw_date}</small></td><td><Balls ticket={row} compact /></td><td className="numeric">{money(row.prizes['1']?.amount)}<small>{row.prizes['1']?.count ?? '—'} 注中奖</small></td><td><span className={`source-dot ${row.conflict ? 'warning' : ''}`} />{sourceNames[row.source] || row.source}<small>{row.sources.length > 1 ? `${row.sources.length} 个来源核对` : `修订版本 ${row.revision}`}</small></td><td><Button className="icon-button" aria-label={`查看 ${row.issue} 期详情`} aria-expanded={expanded} onPress={toggle}><ChevronDown size={16} className={expanded ? 'rotate' : ''} /></Button></td></tr>
    {expanded && <tr className="expanded-row"><td colSpan={5}><div className="prize-grid">{Object.entries(row.prizes).map(([level, prize]) => <div key={level}><span>{level === '7' && row.game === 'ssq' ? '福运奖' : `${level} 等奖`}</span><strong>¥ {money(prize.amount)}</strong><small>{prize.count ?? '—'} 注</small></div>)}</div><div className="source-detail"><span>销售额 ¥{money(row.sales)} · 奖池 ¥{money(row.pool)} · {row.rule_version}</span><a href={row.source_url} target="_blank" rel="noreferrer">查看原始公告 <ExternalLink size={12} /></a></div></td></tr>}
  </>;
}
