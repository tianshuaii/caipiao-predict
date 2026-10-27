from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import platform
import random
import time
from pathlib import Path
from sqlalchemy import select
from .config import RUNTIME
from .domain import GAMES, TZ, next_target
from .ingestion import fingerprint, coverage
from .models import CalendarOverride, Draw, Prediction, Run, Settlement, utcnow
from .predict import STRATEGY
from .selection import select_tickets, selection_metadata, UNIFORM
from .settlement import settle_ticket

ARTIFACTS = RUNTIME / 'artifacts'

@contextmanager
def workflow_lock():
    with (RUNTIME / 'workflow.lock').open('a') as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another workflow is already running') from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def persist_prediction(session, game, now=None):
    now = (now or datetime.now(TZ)).astimezone(TZ)
    started = time.monotonic()
    rows = list(session.scalars(select(Draw).where(Draw.game == game).order_by(Draw.issue)))
    if not rows or any(r.conflict for r in rows):
        raise ValueError('No usable history or unresolved official-source conflict')
    latest = rows[-1]
    if latest.draw_date > now.astimezone(TZ).date():
        raise ValueError('Latest draw is dated in the future')
    if latest.draw_date == now.astimezone(TZ).date() and (now.hour,now.minute)<(21,30):
        raise ValueError('Today draw is not yet due')
    closures = list(session.scalars(select(CalendarOverride.day).where(CalendarOverride.game == game, CalendarOverride.closed.is_(True))))
    issue, day, deadline = next_target(game, latest.issue, latest.draw_date, now, [d.isoformat() for d in closures])
    previous = session.scalar(select(Prediction).where(Prediction.game == game, Prediction.issue == issue))
    from .portfolio import freeze_controls
    from .prospective import freeze_candidates, select_strategy
    if previous:
        freeze_controls(session,previous,now)
        candidates=freeze_candidates(session,previous,now)
        select_strategy(session,game,[f.strategy for f in candidates if not f.error])
        return previous
    snapshot = [{'issue': r.issue, 'revision': r.revision, 'fingerprint': r.fingerprint, 'data': r.data} for r in rows]
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    filename = f'{game}-{digest}.json'
    target = ARTIFACTS / filename
    if not target.exists(): target.write_bytes(encoded)
    code = b''.join(p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))
    seed = random.SystemRandom().randrange(2**63)
    p = Prediction(game=game, issue=issue, draw_date=day, cutoff_issue=latest.issue, strategy=STRATEGY,
        seed=str(seed), tickets=select_tickets(game, seed), dataset_hash=digest, snapshot_path=filename,
        probabilities={k: [GAMES[game][k][1] / GAMES[game][k][0]] * GAMES[game][k][0] for k in ['front','back']},
        provenance={'selection':selection_metadata(UNIFORM),'code_sha256': hashlib.sha256(code).hexdigest(), 'python': platform.python_version(), 'strategy_version': STRATEGY, 'count': 5, 'cost': '10', 'calendar': 'regular-weekdays-with-official-overrides', 'sales_cutoff': deadline.isoformat(), 'coverage': coverage(session,game), 'rationale': '候选策略尚无可靠样本外优势，采用均匀随机基线；号码概率不因历史遗漏改变。'})
    session.add(p)
    session.flush()
    freeze_controls(session,p,now)
    candidates=freeze_candidates(session,p,now)
    if now+timedelta(seconds=time.monotonic()-started)>=deadline:
        raise ValueError('Sales cutoff passed while preparing prediction')
    selected,reason=select_strategy(session,game,[f.strategy for f in candidates if not f.error])
    candidate=next((f for f in candidates if f.strategy==selected and not f.error),None)
    if candidate:
        p.strategy=candidate.strategy
        p.probabilities=candidate.probabilities
        p.tickets=candidate.tickets
        p.provenance={**p.provenance,'selection':candidate.provenance['selection'],'strategy_version':candidate.strategy,'candidate_forecast_id':candidate.id,'rationale':reason+'；概率评分优势不等于整注中奖优势。'}
    return p

def settle(session):
    created = []
    for p in session.scalars(select(Prediction)):
        draw = session.scalar(select(Draw).where(Draw.game == p.game, Draw.issue == p.issue))
        if draw is None or draw.conflict: continue
        old = session.scalar(select(Settlement).where(Settlement.prediction_id == p.id, Settlement.draw_fingerprint == draw.fingerprint))
        if old: continue
        results = []
        for ticket in p.tickets:
            results.append({**ticket, **settle_ticket(p.game,ticket,draw.data)})
        pending = sum(r['amount'] is None for r in results)
        total = sum((Decimal(r['amount']) for r in results if r['amount'] is not None), Decimal(0))
        item = Settlement(prediction_id=p.id, draw_fingerprint=draw.fingerprint, results=results,
            summary={'pending': pending, 'known_amount': str(total), 'amount': None if pending else str(total), 'cost': str(2 * len(results)), 'net': None if pending else str(total - 2 * len(results)), 'winning_tickets': sum(r['level'] is not None for r in results), 'rule_version': draw.data['rule_version']})
        session.add(item)
        session.flush()
        created.append(item.id)
    return created

def run_workflow(notify=False, now=None, kind="nightly"):
    now=(now or datetime.now(TZ)).astimezone(TZ)
    from .db import session_factory
    from .collectors import collect
    with workflow_lock(), session_factory()() as session:
        run = Run(kind=kind, started_at=now.astimezone(timezone.utc).replace(tzinfo=None))
        session.add(run)
        session.commit()
        details = {}
        for game in GAMES:
            try:
                sync = collect(session, game, full=False)
                settled = settle(session)
                from .prospective import score_candidates, select_strategy
                from .portfolio import score_controls
                score_controls(session,game)
                score_candidates(session,game)
                select_strategy(session,game)
                session.commit()  # Settlement must survive a blocked next prediction.
                if not coverage(session, game)['complete']:
                    raise ValueError('Historical inventory is incomplete; run sync --full before predicting')
                from .calendar import load_calendar
                load_calendar(session, now.year)
                p = persist_prediction(session, game, now)
                if p.draw_date.year != now.year:
                    load_calendar(session, p.draw_date.year)
                session.commit()
                details[game] = {'prediction_id': p.id, 'issue': p.issue, 'sync': sync, 'settled': settled, 'pending': data_pending(session,game,now)}
            except Exception as exc:
                session.rollback()
                details[game] = {'error': str(exc)[:250]}
        run.status = 'success' if all('error' not in v for v in details.values()) else 'partial'
        run.details = details
        run.finished_at = utcnow()
        session.commit()
        # Analysis never enqueues a notification, including explicit CLI invocations.
        return {'run_id': run.id, 'status': run.status, 'details': details, 'notification': 'not_queued'}


def data_pending(session,game,now):
    """Require the latest expected draw and its published prize amounts/counts."""
    day=now.astimezone(TZ).date()
    if (now.hour,now.minute)<(21,30): day-=timedelta(days=1)
    from .calendar import load_calendar
    load_calendar(session,day.year)
    closed=set(session.scalars(select(CalendarOverride.day).where(CalendarOverride.game==game,CalendarOverride.closed.is_(True))))
    for _ in range(60):
        if day.weekday() in GAMES[game]['days'] and day not in closed: break
        day-=timedelta(days=1)
    row=session.scalar(select(Draw).where(Draw.game==game).order_by(Draw.issue.desc()).limit(1))
    if not row or row.conflict or row.draw_date<day: return True
    prizes=row.data.get('prizes',{})
    version=row.data['rule_version']
    levels=6 if game=='ssq' or version=='dlt-classic' else (9 if version=='dlt-2019019' else 7)
    return any(str(i) not in prizes for i in range(1,levels+1)) or any(p.get('amount') is None or p.get('count') is None for p in prizes.values())
