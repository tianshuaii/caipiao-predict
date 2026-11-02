from datetime import date
import hashlib
import json
from sqlalchemy import select
from .domain import GAMES
from .game_specs import draw_zones, validate_draw
from .game_specs import game_spec
from .models import Draw, Observation, Run, utcnow

def fingerprint(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def ingest(session, data, raw_id, source):
    validate_draw(data['game'], data['issue'], draw_zones(data))
    digest = fingerprint(data)
    row = session.scalar(select(Draw).where(Draw.game == data['game'], Draw.issue == data['issue']))
    if row is None:
        row = Draw(game=data['game'], issue=data['issue'], draw_date=date.fromisoformat(data['draw_date']), data=data, source=source, raw_id=raw_id, fingerprint=digest, sources=[source], revision=1, conflict=False)
        session.add(row)
        session.flush()
    previous = session.scalar(select(Observation).where(Observation.draw_id == row.id, Observation.source == source, Observation.fingerprint == digest))
    if previous and row.fingerprint == digest:
        return row
    mismatch = row.data['draw_date'] != data['draw_date'] or draw_zones(row.data) != draw_zones(data)
    conflict = mismatch and row.source != source
    last = session.scalar(select(Observation).where(Observation.draw_id == row.id, Observation.source == source).order_by(Observation.id.desc()).limit(1))
    new_conflict = conflict and (not last or not last.conflict or last.fingerprint != digest)
    if not previous or (row.source == source and row.fingerprint != digest) or new_conflict: session.add(Observation(draw_id=row.id, raw_id=raw_id, source=source, fingerprint=digest, data=data, conflict=conflict))
    row.sources = sorted(set(row.sources + [source]))
    if conflict:
        row.conflict = True
    elif row.source == source and row.fingerprint != digest:
        row.data, row.fingerprint, row.raw_id = data, digest, raw_id
        row.draw_date = date.fromisoformat(data['draw_date'])
        row.revision += 1
    # Secondary observations corroborate numbers, but cannot erase canonical prize metadata.
    row.updated_at = utcnow()
    session.flush()
    return row

def coverage(session, game):
    rows = list(session.scalars(select(Draw).where(Draw.game == game).order_by(Draw.issue)))
    if not rows:
        return {'count': 0, 'complete': False, 'missing_count': 0, 'missing': [], 'first_issue': None, 'last_issue': None, 'conflicts': 0, 'prize_complete_count': 0}
    first_year = int((GAMES[game]['first'] if game in GAMES else game_spec(game, rows[0].issue).first)[:4])
    by_year = {}
    for row in rows: by_year.setdefault(int(row.issue[:4]), set()).add(int(row.issue[-3:]))
    missing = []
    missing_years = []
    for year in range(first_year, int(rows[-1].issue[:4]) + 1):
        seq = by_year.get(year, set())
        if not seq:
            missing_years.append(year)
        else:
            missing.extend(f'{year}{i:03d}' for i in range(1, max(seq) + 1) if i not in seq)
    inventory = list(session.scalars(select(Run).where(Run.kind == 'inventory', Run.status == 'success').order_by(Run.id)))
    sources = {}
    for audit in inventory:
        if audit.details.get('game') == game: sources[audit.details['source']] = audit.details['issues']
    expected = set().union(*(set(v) for v in sources.values())) if sources else set()
    missing = sorted(set(missing) | (expected - {r.issue for r in rows}))
    inventory_verified = bool(expected) and rows[0].issue in expected
    conflicts = sum(r.conflict for r in rows)
    levels = 7 if game == 'qlc' else 6 if game == 'qxc' else 7 if game == 'ssq' else (8 if rows[-1].issue >= '2026014' else 10 if rows[-1].issue >= '2019019' else 7)
    prize_complete = sum(all(r.data['prizes'].get(str(i), {}).get('amount') is not None and r.data['prizes'].get(str(i), {}).get('count') is not None for i in range(1, levels + 1)) for r in rows)
    first_issue = GAMES[game]['first'] if game in GAMES else game_spec(game, rows[0].issue).first
    return {'count': len(rows), 'inventory_verified': inventory_verified, 'complete': inventory_verified and not missing and not missing_years and not conflicts and rows[0].issue == first_issue, 'first_issue': rows[0].issue, 'last_issue': rows[-1].issue, 'missing': missing[:100], 'missing_count': len(missing) + len(missing_years), 'missing_years': missing_years, 'conflicts': conflicts, 'prize_complete_count': prize_complete, 'note': '完整性按首期、年份、年内期号及官方分页核查；缺失奖金保持未知。'}

def record_inventory(session, game, source, issues):
    session.add(Run(kind='inventory', status='success', finished_at=utcnow(), details={'game':game,'source':source,'issues':sorted(issues)}))
    session.commit()
