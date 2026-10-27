import type { Ticket } from '../api';

export function Balls({ ticket, actual, compact = false }: { ticket: Ticket; actual?: Ticket | null; compact?: boolean }) {
  return <div className={`balls ${compact ? 'compact' : ''}`} aria-label={`前区或红球 ${ticket.front.join('、')}，后区或蓝球 ${ticket.back.join('、')}`}>
    {ticket.front.map(n => <span key={`f${n}`} className={`ball front ${actual && !actual.front.includes(n) ? 'miss' : ''} ${actual?.front.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
    <span className="ball-divider" aria-hidden="true">+</span>
    {ticket.back.map(n => <span key={`b${n}`} className={`ball back ${actual && !actual.back.includes(n) ? 'miss' : ''} ${actual?.back.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
  </div>;
}
