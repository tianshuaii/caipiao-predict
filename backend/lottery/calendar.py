"""Reviewed official holiday calendar, versioned alongside the application."""
from datetime import date, timedelta
import json
from sqlalchemy import select
from .config import ROOT
from .models import CalendarOverride
from .game_specs import registered_games

def load_calendar(session,year):
    calendar=json.loads((ROOT/'config/calendar.json').read_text())
    entry=calendar.get(str(year))
    if not entry: raise ValueError(f'{year} official holiday calendar requires review in config/calendar.json')
    if set(entry.get('games', ())) != set(registered_games()):
        raise ValueError(f'{year} calendar must review every registered game')
    for begin,end in entry['closed_ranges']:
        day,last=date.fromisoformat(begin),date.fromisoformat(end)
        if day.year!=year or last.year!=year or last<day: raise ValueError('Invalid holiday range')
        while day<=last:
            for game in registered_games():
                row=session.scalar(select(CalendarOverride).where(CalendarOverride.game==game,CalendarOverride.day==day))
                if not row:
                    session.add(CalendarOverride(game=game,day=day,closed=True,source_url=entry['source_url'],note='官方年度休市公告'))
            day+=timedelta(days=1)
    session.flush()
