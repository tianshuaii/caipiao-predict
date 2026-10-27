"""Read-only quality and historical visibility of observations actually retained."""
from datetime import date, datetime, timezone
from sqlalchemy import select
from .domain import TZ
from .models import Draw, Observation
from .ingestion import coverage


def naive_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def history_as_of(session,game,as_of,before_issue=None):
    cutoff=naive_utc(as_of)
    local_day=cutoff.replace(tzinfo=timezone.utc).astimezone(TZ).date()
    draws=list(session.scalars(select(Draw).where(Draw.game==game).order_by(Draw.issue)))
    if before_issue is not None: draws=[d for d in draws if d.issue<before_issue]
    rows=list(session.scalars(select(Observation).join(Draw).where(Draw.game==game).order_by(Observation.created_at,Observation.id)))
    groups={}
    for row in rows: groups.setdefault(row.draw_id,[]).append(row)
    items=[];unknown=0;conflicts=0
    for draw in draws:
        all_rows=groups.get(draw.id,[])
        visible=[r for r in all_rows if r.created_at<=cutoff]
        if not visible:
            if draw.draw_date<=local_day: unknown+=1
            continue
        # The first observed source is canonical; do not consult future revisions.
        source=visible[0].source
        canonical=[r for r in visible if r.source==source][-1]
        if date.fromisoformat(canonical.data['draw_date'])>local_day: continue
        # No historical conflict-resolution events exist yet: fail closed.
        if any(r.conflict for r in visible):
            conflicts+=1;continue
        items.append({**canonical.data,'fingerprint':canonical.fingerprint,'source':source,
                      'observed_at':canonical.created_at.isoformat()+'Z','conflict':False})
    return {'game':game,'as_of':cutoff.isoformat()+'Z','items':items,'total':len(items),
            'unavailable_count':unknown,'conflicts':conflicts,
            'mode':'retained-observations-only',
            'note':'仅还原实际保存的观测，不以开奖日期推断当时已采集。缺少观测时期不可回溯；历史冲突无明确解除事件时排除。'}


def quality_view(session,game,now=None):
    now=naive_utc(now or datetime.now(timezone.utc))
    report=coverage(session,game)
    latest=session.scalar(select(Draw).where(Draw.game==game).order_by(Draw.issue.desc()).limit(1))
    first=session.scalar(select(Observation.created_at).join(Draw).where(Draw.game==game).order_by(Observation.created_at).limit(1))
    last=session.scalar(select(Observation.created_at).join(Draw).where(Draw.game==game).order_by(Observation.created_at.desc()).limit(1))
    return {**report,'draw_count':report['count'],
            'prize_complete_rate':report['prize_complete_count']/report['count'] if report['count'] else None,
            'latest_draw_date':latest.draw_date.isoformat() if latest else None,
            'first_observed_at':first.isoformat()+'Z' if first else None,
            'last_observed_at':last.isoformat()+'Z' if last else None,
            'observation_age_seconds':max(0,(now-last).total_seconds()) if last else None,
            'history_mode':'retained-observations-only'}
