import type { Ticket } from '../api';

export function Balls({ ticket, actual, compact = false }: { ticket: Ticket; actual?: Ticket | null; compact?: boolean }) {
  const values = ticket.zones ? { ...ticket, ...ticket.zones } : ticket;
  const actualValues = actual?.zones ? { ...actual, ...actual.zones } : actual;
  if (values.basic && values.special) return <div className={`balls ${compact ? 'compact' : ''}`} aria-label={`基本号 ${values.basic.join('、')}，特别号 ${values.special.join('、')}`}>
    {values.basic.map(n => <span key={`b${n}`} className={`ball front ${actualValues && !actualValues.basic?.includes(n) ? 'miss' : ''} ${actualValues?.basic?.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
    <span className="ball-divider" aria-hidden="true">+</span>
    {values.special.map(n => <span key={`s${n}`} className={`ball back ${actualValues && !actualValues.special?.includes(n) ? 'miss' : ''} ${actualValues?.special?.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
  </div>;
  if (values.positions) return <div className={`balls ${compact ? 'compact' : ''}`} aria-label={`七星彩 ${values.positions.join('、')}`}>
    {values.positions.map((n, index) => <span key={`p${index}`} className={`ball ${index === 6 ? 'back' : 'front'} ${actualValues && actualValues.positions?.[index] !== n ? 'miss' : ''} ${actualValues?.positions?.[index] === n ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
  </div>;
  return <div className={`balls ${compact ? 'compact' : ''}`} aria-label={`前区或红球 ${values.front.join('、')}，后区或蓝球 ${values.back.join('、')}`}>
    {values.front.map(n => <span key={`f${n}`} className={`ball front ${actualValues && !actualValues.front.includes(n) ? 'miss' : ''} ${actualValues?.front.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
    <span className="ball-divider" aria-hidden="true">+</span>
    {values.back.map(n => <span key={`b${n}`} className={`ball back ${actualValues && !actualValues.back.includes(n) ? 'miss' : ''} ${actualValues?.back.includes(n) ? 'hit' : ''}`}>{String(n).padStart(2, '0')}</span>)}
  </div>;
}
