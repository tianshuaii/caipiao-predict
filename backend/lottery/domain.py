"""Pure rules. Award amounts always come from the draw's official bulletin."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
GAMES = {
    'dlt': {'name': '超级大乐透', 'front': (35, 5), 'back': (12, 2), 'days': (0, 2, 5), 'first': '2007001'},
    'ssq': {'name': '双色球', 'front': (33, 6), 'back': (16, 1), 'days': (1, 3, 6), 'first': '2003001'},
}

def canonical_issue(issue):
    value = str(issue)
    if len(value) == 5:
        value = '20' + value
    if len(value) != 7 or not value.isdigit() or int(value[-3:]) < 1:
        raise ValueError('Invalid issue number')
    return value

def validate_ticket(game, front, back):
    if game not in GAMES:
        raise ValueError('Unknown game')
    for key, values in [('front', front), ('back', back)]:
        maximum, count = GAMES[game][key]
        if len(values) != count or len(set(values)) != count:
            raise ValueError('Wrong number count or duplicate number')
        if any(type(v) is not int or not 1 <= v <= maximum for v in values):
            raise ValueError('Number out of range')

def rule_version(game, issue):
    issue = canonical_issue(issue)
    if game == 'ssq':
        return 'ssq-2026014' if issue >= '2026014' else 'ssq-classic'
    return 'dlt-2026014' if issue >= '2026014' else ('dlt-2019019' if issue >= '2019019' else 'dlt-classic')

def prize_level(game, issue, front_hits, back_hits):
    pair = (front_hits, back_hits)
    if game == 'ssq':
        if front_hits == 6: return 1 if back_hits else 2
        if pair == (5, 1): return 3
        if pair in [(5, 0), (4, 1)]: return 4
        if pair in [(4, 0), (3, 1)]: return 5
        return 6 if back_hits == 1 else None
    version = rule_version(game, issue)
    if version == 'dlt-2026014':
        groups = [[(5,2)], [(5,1)], [(5,0),(4,2)], [(4,1)], [(4,0),(3,2)], [(3,1),(2,2)], [(3,0),(2,1),(1,2),(0,2)]]
    elif version == 'dlt-2019019':
        groups = [[(5,2)], [(5,1)], [(5,0)], [(4,2)], [(4,1)], [(3,2)], [(4,0)], [(3,1),(2,2)], [(3,0),(2,1),(1,2),(0,2)]]
    else:
        groups = [[(5,2)], [(5,1)], [(5,0),(4,2)], [(4,1),(3,2)], [(4,0),(3,1),(2,2)], [(3,0),(2,1),(1,2),(0,2)]]
    return next((n for n, group in enumerate(groups, 1) if pair in group), None)

def next_target(game, last_issue, last_date, now, closures=()):
    """Fail closed when an expected draw is missing or sales have closed.

    Official holiday overrides are passed explicitly. Never skip an unpublished draw.
    """
    now = now.astimezone(TZ)
    day = last_date + timedelta(days=1)
    for _ in range(60):
        if day.weekday() in GAMES[game]['days'] and day.isoformat() not in closures:
            break
        day += timedelta(days=1)
    else:
        raise ValueError('Unable to determine next draw date')
    deadline = datetime.combine(day, time(20, 0), TZ)  # conservative local cutoff
    if now >= deadline:
        raise ValueError('Latest expected draw is missing or target sales have closed')
    issue = f'{day.year}{1 if day.year != last_date.year else int(canonical_issue(last_issue)[-3:]) + 1:03d}'
    return issue, day, deadline
