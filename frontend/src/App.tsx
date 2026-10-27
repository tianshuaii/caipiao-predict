import { strategyName } from './strategies';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@heroui/react';
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, CircleHelp, Clock3, Database, FlaskConical, History, LayoutDashboard, ListChecks, Menu, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { get, type Draw, type Experiment, type Game, type Overview, type Prediction, type Tasks, type StrategyStatus } from './api';
import { ResearchPanel } from './components/ResearchPanel';
import { WinnerCasesPanel } from './components/WinnerCasesPanel';
import { StrategyPanel } from './components/StrategyPanel';
import { Balls } from './components/Balls';
import { DrawTable, money } from './components/DrawTable';

const pages = [
  { id: 'overview', label: '数据概览', icon: LayoutDashboard, eyebrow: 'OVERVIEW', title: '把每一期，研究清楚。' },
  { id: 'draws', label: '开奖档案', icon: Database, eyebrow: 'DRAW ARCHIVE', title: '从第一期开始，有据可查。' },
  { id: 'review', label: '预测与复盘', icon: History, eyebrow: 'PREDICTIONS & REVIEW', title: '留下预测，也记录结果。' },
  { id: 'experiments', label: '策略实验室', icon: FlaskConical, eyebrow: 'EXPERIMENTS', title: '用证据检验每一个想法。' },
  { id: 'research', label: '约束选号研究', icon: FlaskConical, eyebrow: 'SELECTION RESEARCH', title: '把条件，变成可复现的实验。' },
  { id: 'cases', label: '一等奖票型', icon: ListChecks, eyebrow: 'WINNING TICKET REPORTS', title: '看看公开报道中的中奖彩票。' },
  { id: 'tasks', label: '运行记录', icon: ListChecks, eyebrow: 'SYSTEM ACTIVITY', title: '每一次更新，都有记录。' },
];
const gameNames = { dlt: '超级大乐透', ssq: '福彩双色球' };
const statusNames: Record<string, string> = { success: '已完成', partial: '部分完成', failed: '失败', running: '运行中', sent: '通道已受理', pending: '等待发送', not_configured: '未配置', uncertain: '送达待确认', sending: '发送待确认' };
const dateTime = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '—';

export default function App({ onLogout }: { onLogout?: () => void }) {
  const [page, setPage] = useState('overview');
  const [game, setGame] = useState<Game>('dlt');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [rows, setRows] = useState<Draw[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [strategies, setStrategies] = useState<StrategyStatus | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [tasks, setTasks] = useState<Tasks | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [menu, setMenu] = useState(false);
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(() => setRevision(v => v + 1), []);
  useEffect(() => { const timer = setInterval(refresh, 60000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => { setRows([]); setPredictions([]); setExperiments([]); setStrategies(null); }, [game, page, offset]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError('');
    async function load() {
      const requests: Promise<unknown>[] = [get<Overview>('/overview', controller.signal).then(setOverview)];
      if (page === 'draws') requests.push(get<{ items: Draw[]; total: number }>(`/draws?game=${game}&offset=${offset}`, controller.signal).then(r => { setRows(r.items); setTotal(r.total); }));
      if (page === 'review') requests.push(get<{ items: Prediction[] }>(`/predictions?game=${game}`, controller.signal).then(r => setPredictions(r.items)));
      if (page === 'experiments') requests.push(get<{ items: Experiment[] }>(`/experiments?game=${game}`, controller.signal).then(r => setExperiments(r.items)));
      if (page === 'experiments') requests.push(get<StrategyStatus>(`/strategies?game=${game}`, controller.signal).then(setStrategies));
      if (page === 'tasks') requests.push(get<Tasks>('/tasks', controller.signal).then(setTasks));
      await Promise.all(requests);
    }
    load().catch(e => { if (e.name !== 'AbortError') setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, game, offset, revision]);
  const current = overview?.games[game];
  const pageMeta = pages.find(p => p.id === page)!;
  const totalHistory = overview ? Object.values(overview.games).reduce((s, g) => s + g.coverage.count, 0) : 0;

  function navigate(id: string) { setPage(id); setMenu(false); }
  return <div className="app-shell">
    {menu && <button className="mobile-overlay" aria-label="关闭导航" onClick={() => setMenu(false)} />}
    <aside className={`sidebar ${menu ? 'open' : ''}`}>
      <a className="brand" href="#" onClick={e => { e.preventDefault(); navigate('overview'); }}><span className="brand-mark"><span /><span /><span /><span /></span><span>拾数<small>LOTTERY LAB</small></span></a>
      <div className="workspace-label">个人研究空间 <span>LOCAL</span></div>
      <nav aria-label="主导航">{pages.map(p => <Button key={p.id} className={`nav-item ${page === p.id ? 'active' : ''}`} aria-current={page === p.id ? 'page' : undefined} onPress={() => navigate(p.id)}><p.icon size={19} strokeWidth={1.6} /><span>{p.label}</span>{page === p.id && <span className="nav-indicator" />}</Button>)}</nav>
      <div className="sidebar-note"><div className="note-icon"><FlaskConical size={19} /></div><strong>保持好奇，也尊重随机。</strong><p>以官方数据为依据，<br />让每个结论都可以被检验。</p></div>
      <div className="sidebar-footer"><span className={`source-dot ${!overview?.schedule.scheduler.running ? 'warning' : ''}`} /><span>{overview?.schedule.scheduler.running ? '本地调度运行中' : '本地研究模式'}<small>Asia / Shanghai</small></span><ShieldCheck size={17} /></div>
    </aside>
    <main>
      <header className="topbar"><div className="breadcrumb"><Button className="icon-button mobile-menu" aria-label="打开导航" onPress={() => setMenu(true)}><Menu size={20} /></Button><span>研究工作台</span><ChevronRight size={13} /><strong>{pageMeta.label}</strong></div><div className="topbar-right"><span className="local-badge"><span /> LOCAL WORKSPACE</span><span className="avatar">田</span>{onLogout && <Button className="text-button" onPress={onLogout}>退出登录</Button>}</div></header>
      <div className="main-content">
        <section className="page-heading"><div><div className="eyebrow">{pageMeta.eyebrow}<span />LOTTERY RESEARCH</div><h1>{pageMeta.title}</h1><p>官方数据、可追溯预测与统计实验，在一个清晰的工作台里。</p></div><Button className="refresh-button" onPress={refresh} isDisabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} />{loading ? '更新中' : '刷新数据'}</Button></section>
        {error && <div className="error-banner" role="alert"><Activity size={18} /><span>{error} {overview && '当前展示上次成功加载的数据。'}</span><Button className="text-button" onPress={refresh}>重试</Button></div>}
        {!overview && !error && <div className="loading-state"><span className="loader" />正在读取本地研究数据…</div>}
        {overview && <>
          <div className="context-bar"><div className="game-switch" aria-label="选择彩种">{(['dlt', 'ssq'] as Game[]).map(g => <Button key={g} className={game === g ? 'selected' : ''} aria-pressed={game === g} onPress={() => { setGame(g); setOffset(0); }}><span className={`game-dot ${g}`} />{gameNames[g]}</Button>)}</div><span className="last-update"><Clock3 size={13} />更新于 {dateTime(overview.generated_at)}</span></div>
          {page === 'overview' && current && <>
            <div className="metric-grid">
              <Metric label="历史数据总量" value={totalHistory.toLocaleString()} unit="期" icon={<Database size={19} />} footer={`${current.coverage.count.toLocaleString()} 期${gameNames[game]} · ${current.coverage.complete ? '号码覆盖完整' : '部分历史待补齐'}`} />
              <Metric label="最新开奖期次" value={current.latest?.issue || '—'} icon={<CalendarDays size={19} />} footer={current.latest ? `${current.latest.draw_date} · 官方结果已入库` : '等待首次同步'} />
              <Metric label="正式预测记录" value={String(current.stats.predictions)} unit="期" icon={<Sparkles size={19} />} footer={`${current.stats.settled_periods} 期已结算 · 每期 5 注单式`} />
              <Metric label="已结算模拟净收益" value={current.stats.settled_periods ? `${current.stats.net >= 0 ? '+' : ''}${money(current.stats.net)}` : '—'} unit={current.stats.settled_periods ? '元' : ''} icon={<BarChart3 size={19} />} footer={current.stats.settled_periods ? `已结算成本 ¥${money(current.stats.settled_cost)}` : '积累前瞻样本后展示'} />
            </div>
            <div className="prediction-grid"><section className="panel prediction-panel"><PanelHeading title="下一期 · 参考号码" subtitle="PREDICTION" right={<span className="pill purple">5 注单式</span>} />
              {current.prediction ? <PredictionCard prediction={current.prediction} /> : <div className="empty"><Sparkles size={26} /><strong>等待首次预测</strong><p>完成官方数据检查后，正式号码会在这里出现。</p></div>}
            </section><section className="panel draw-panel"><PanelHeading title="最近一期开奖" subtitle="LATEST DRAW" right={<span className="pill green"><Check size={12} />官方数据</span>} />{current.latest ? <><div className="latest-issue"><span>第 <strong>{current.latest.issue}</strong> 期</span><span>{current.latest.draw_date}</span></div><Balls ticket={current.latest} /><div className="draw-money"><div><span>一等奖单注奖金</span><strong>¥ {money(current.latest.prizes['1']?.amount)}</strong></div><div><span>一等奖注数</span><strong>{current.latest.prizes['1']?.count ?? '—'}<small> 注</small></strong></div></div><div className="pool-row"><span>滚存奖池</span><strong>{current.latest.pool ? `${(Number(current.latest.pool) / 1e8).toFixed(2)} 亿元` : '待公布'}</strong></div></> : <div className="empty">等待官方开奖数据</div>}<div className="schedule-box"><div className="schedule-icon"><Clock3 size={20} /></div><div><strong>{overview.schedule.label}</strong><p>更新开奖 → 复盘 → 预测 → 微信通知</p><small>下次计划 {dateTime(overview.schedule.next_run)}</small></div></div></section></div>
            <div className="analysis-grid"><section className="panel"><PanelHeading title="最近 20 期 · 号码和值" subtitle="DRAW DISTRIBUTION" right={<span className="chart-legend"><span />{game === 'ssq' ? '红球' : '前区'}和值</span>} /><div className="chart-wrap"><ResponsiveContainer width="100%" height={210}><AreaChart data={[...current.recent].reverse().map(r => ({ issue: r.issue.slice(-3), sum: r.front.reduce((a, b) => a + b, 0) }))} margin={{ top: 8, right: 12, left: -20, bottom: 0 }}><defs><linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7771ee" stopOpacity={0.2} /><stop offset="100%" stopColor="#7771ee" stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#eaeaf1" /><XAxis dataKey="issue" tick={{ fontSize: 11, fill: '#9294a5' }} axisLine={false} tickLine={false} minTickGap={20} /><YAxis tick={{ fontSize: 11, fill: '#9294a5' }} axisLine={false} tickLine={false} /><Tooltip formatter={value => [value, '和值']} labelFormatter={label => `第 ${label} 期`} contentStyle={{ borderRadius: 10, border: '1px solid #ebebf1', fontSize: 12 }} /><Area type="monotone" dataKey="sum" stroke="#7771ee" strokeWidth={2.4} fill="url(#areaFill)" isAnimationActive={false} /></AreaChart></ResponsiveContainer></div><p className="chart-footnote">走势仅描述历史分布，不代表下一期的开奖方向。</p></section><section className="panel"><PanelHeading title="号码出现频次" subtitle="LAST 20 DRAWS" /><div className="frequency-grid">{current.frequency.map(f => <div key={f.number} className="frequency-cell" style={{ background: `rgba(111, 103, 228, ${0.045 + f.count / 20 * 0.5})` }} title={`号码 ${f.number}：出现 ${f.count} 次`}><strong>{String(f.number).padStart(2, '0')}</strong><span>{f.count} 次</span></div>)}</div><p className="chart-footnote">{game === 'ssq' ? '红球' : '前区'}号码 · 颜色深浅表示出现频次</p></section></div>
            <section className="panel"><PanelHeading title="最近 20 期开奖档案" subtitle="RECENT DRAWS" right={<Button className="text-button" onPress={() => navigate('draws')}>全部 {current.coverage.count.toLocaleString()} 期 <ChevronRight size={14} /></Button>} /><DrawTable rows={current.recent} /></section>
          </>}
          {page === 'draws' && current && <section className="panel"><PanelHeading title={`${gameNames[game]} · 历史开奖`} subtitle={`${current.coverage.first_issue || '—'} — ${current.coverage.last_issue || '—'}`} right={<span className="pill purple">共 {total.toLocaleString()} 期</span>} /><div aria-busy={loading}><DrawTable rows={rows} /></div><div className="pagination"><span>第 {offset + 1}–{Math.min(offset + 20, total)} 条 / 共 {total} 条</span><div><Button className="pagination-button" isDisabled={offset === 0 || loading} onPress={() => setOffset(v => Math.max(0, v - 20))}><ChevronLeft size={16} />上一页</Button><Button className="pagination-button" isDisabled={offset + 20 >= total || loading} onPress={() => setOffset(v => v + 20)}>下一页<ChevronRight size={16} /></Button></div></div></section>}
          {page === 'review' && <div className="review-list">{predictions.length ? predictions.map(p => <section className="panel" key={p.id}><PanelHeading title={`第 ${p.issue} 期 · ${gameNames[p.game]}`} subtitle={`生成于 ${dateTime(p.created_at)} · 开奖 ${p.draw_date}`} right={<span className={`pill ${p.settlement ? 'green' : 'purple'}`}>{p.settlement ? '已复盘' : p.actual ? '等待结算' : '等待开奖'}</span>} /><PredictionCard prediction={p} review /><details className="provenance"><summary>查看溯源信息</summary><dl><dt>训练 / 输入截止期</dt><dd>{p.cutoff_issue}</dd><dt>策略与随机种子</dt><dd>{p.strategy} / {p.seed}</dd><dt>数据快照 SHA256</dt><dd>{p.dataset_hash}</dd><dt>代码 SHA256</dt><dd>{p.provenance.code_sha256}</dd></dl></details></section>) : <section className="panel empty"><History size={28} /><strong>还没有正式预测记录</strong><p>开奖前生成的每一批号码都会保留在这里，开奖后自动核对。</p></section>}</div>}
          {page === 'experiments' && <><StrategyPanel data={strategies} /><ExperimentView experiments={experiments} /></>}
          {page === 'research' && <ResearchPanel key={game} game={game} />}
          {page === 'cases' && <WinnerCasesPanel key={game} game={game} revision={revision} />}
          {page === 'tasks' && tasks && <TaskView tasks={tasks} />}
          <footer className="page-footer"><span><ShieldCheck size={13} /> 官方来源 · 预测留痕 · 独立回测</span><span>公平独立开奖下，历史数据不能保证提高中奖概率。所有收益均为模拟。</span></footer>
        </>}
      </div>
    </main>
  </div>;
}

function Metric({ label, value, unit, icon, footer }: { label: string; value: string; unit?: string; icon: React.ReactNode; footer: string }) { return <section className="metric"><div className="metric-label">{label}<span>{icon}</span></div><div className="metric-value">{value}<small>{unit}</small></div><p>{footer}</p></section>; }
function PanelHeading({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) { return <div className="panel-heading"><div>{subtitle && <span className="section-eyebrow">{subtitle}</span>}<h2>{title}</h2></div>{right}</div>; }

function PredictionCard({ prediction: p, review = false }: { prediction: Prediction; review?: boolean }) {
  return <><div className="prediction-meta"><span>第 <strong>{p.issue}</strong> 期</span><span>{p.draw_date} 开奖{p.actual ? ' · 已开奖' : ''}</span></div><div className="tickets">{p.tickets.map((ticket, i) => { const result = p.settlement?.results[i]; return <div className="ticket" key={i}><span className="ticket-index">{String(i + 1).padStart(2, '0')}</span><Balls ticket={ticket} actual={review ? p.actual : null} compact /><span className={`ticket-result ${result?.level ? 'win' : ''}`}>{review && result ? `${result.front_hits}+${result.back_hits} · ${result.level ? `${result.level}等奖 ¥${money(result.amount)}` : '未中奖'}` : '单式'}</span></div>; })}</div>{review && p.actual && <div className="actual-result"><span>实际开奖</span><Balls ticket={p.actual} compact /></div>}{review && p.settlement && <div className="settlement-summary"><span>模拟成本 ¥{money(p.settlement.summary.cost)}</span><span>已确认奖金 ¥{money(p.settlement.summary.known_amount)}</span><strong>{p.settlement.summary.pending ? `${p.settlement.summary.pending} 注金额待公布` : `净收益 ¥${money(p.settlement.summary.net)}`}</strong></div>}<div className="prediction-foot"><ShieldCheck size={14} /><span>数据截止 {p.cutoff_issue} · {p.strategy} · 已冻结入库</span></div></>;
}

function ExperimentView({ experiments }: { experiments: Experiment[] }) {
  const latest = experiments[0];
  if (!latest) return <section className="panel empty"><FlaskConical size={30} /><strong>等待第一份实验报告</strong><p>使用按时间滚动的样本外回测，与相同注数的随机基线比较。</p></section>;
  return <><section className="experiment-intro"><div><span className="pill purple">探索性研究</span><h2>一个模型，需要比“看起来有效”更有说服力。</h2><p>历史回测仅作探索性比较；正式策略根据上方独立前瞻验证决定。</p></div><div className="experiment-count"><strong>{latest.evaluation_periods}</strong><span>期计划验证</span></div></section><section className="panel"><PanelHeading title="策略对照实验" subtitle={`${latest.from_issue} — ${latest.to_issue} · ${latest.protocol.version}`} /><div className="table-scroll"><table className="experiment-table"><thead><tr><th>策略</th><th>Brier 分数 ↓</th><th>平均命中球数 / 注</th><th>模拟成本</th><th>已知模拟奖金</th><th>校正 p 值</th></tr></thead><tbody>{latest.strategies.map(s => <tr key={s.strategy}><td><strong>{strategyName(s.strategy)}</strong>{s.strategy === 'uniform' && <small>对照基线</small>}{s.evaluated_periods != null && <small>共同有效 {s.evaluated_periods} 期 · 本模型失败 {s.failed_periods ?? 0} 期</small>}</td><td>{s.brier?.toFixed(6) ?? '暂无有效样本'}</td><td>{s.mean_hits?.toFixed(3) ?? '—'}</td><td>¥{money(s.cost)}</td><td>¥{money(s.known_return)}{s.pending_tickets > 0 && <small>{s.pending_tickets} 注待结算</small>}</td><td>{s.holm_p == null ? '基准' : s.holm_p.toFixed(4)}</td></tr>)}</tbody></table></div><div className="experiment-notes">{latest.comparison && <p>共同有效 {latest.comparison.issues.length} 期，排除 {latest.comparison.excluded.length} 期；详细原因保留于实验报告。</p>}<p><CircleHelp size={16} />Brier 分数衡量号码边际概率误差，越小越好；它不是整注中奖概率。</p><p>{latest.random_simulations} 次随机模拟的平均命中球数 95% 参考区间：{latest.random_hit_interval?.map(x => x.toFixed(3)).join(' – ') ?? '暂无共同有效样本'}。同注数、同成本比较。</p><p>训练及校准只使用目标期之前的数据；多个候选比较采用 Holm 校正，历史回测不触发自动切换，前瞻门槛见上方。</p></div></section><section className="panel"><PanelHeading title="实验记录" subtitle="EXPERIMENT LOG" /><div className="experiment-log">{experiments.map(e => <div key={e.id}><FlaskConical size={18} /><div><strong>#{e.id} · {e.from_issue} — {e.to_issue}</strong><p>{e.evaluation_periods} 期验证 · {dateTime(e.created_at)}</p></div><span className="pill neutral">可复现</span></div>)}</div></section></>;
}

function TaskView({ tasks }: { tasks: Tasks }) {
  return <><div className="system-banner"><Clock3 size={25} /><div><strong>{tasks.schedule.label} · 北京时间</strong><p>下次计划执行 {dateTime(tasks.schedule.next_run)}</p></div><span className={`pill ${tasks.schedule.scheduler.running ? 'green' : 'orange'}`}>{tasks.schedule.scheduler.running ? '调度器在线' : '调度器未运行'}</span></div><section className="panel"><PanelHeading title="微信通知" subtitle="SERVER CHAN" /><div className="notification-list">{tasks.notifications.length ? tasks.notifications.map(n => <div key={n.id}><div className="notification-icon"><Check size={18} /></div><div><strong>{n.title}</strong><p>{n.detail || '等待发送'} · {dateTime(n.created_at)}</p></div><span className={`pill ${n.status === 'sent' ? 'green' : 'orange'}`}>{statusNames[n.status] || n.status}</span></div>) : <div className="empty">尚无通知记录</div>}</div></section><section className="panel"><PanelHeading title="任务执行记录" subtitle="RUN HISTORY" /><div className="task-list">{tasks.runs.map(r => <details key={r.id}><summary><span className={`activity-dot ${r.status}`} /><div><strong>#{r.id} · {r.kind === 'inventory' ? '全量期号校验' : r.kind === 'history' ? '历史数据采集' : r.kind === 'scheduled' ? '开奖复盘与下期预测' : r.kind}</strong><small>{dateTime(r.started_at)}</small></div><span className={`pill ${r.status === 'success' ? 'green' : 'orange'}`}>{statusNames[r.status]}</span><ChevronRight size={15} /></summary><pre>{JSON.stringify(r.details, null, 2)}</pre></details>)}</div></section></>;
}
