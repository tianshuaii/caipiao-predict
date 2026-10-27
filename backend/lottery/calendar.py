"""Reviewed official holiday calendar, versioned alongside the application."""
from datetime import date, timedelta
import json
from sqlalchemy import select
from .config import ROOT
from .models import CalendarOverride

def load_calendar(session,year):
    calendar=json.loads((ROOT/'config/calendar.json').read_text())
    entry=calendar.get(str(year))
    if not entry: raise ValueError(f'{year} official holiday calendar requires review in config/calendar.json')
    for begin,end in entry['closed_ranges']:
        day,last=date.fromisoformat(begin),date.fromisoformat(end)
        if day.year!=year or last.year!=year or last<day: raise ValueError('Invalid holiday range')
        while day<=last:
            for game in ['dlt','ssq']:
                row=session.scalar(select(CalendarOverride).where(CalendarOverride.game==game,CalendarOverride.day==day))
                if not row:
                    session.add(CalendarOverride(game=game,day=day,closed=True,source_url=entry['source_url'],note='官方年度休市公告'))
            day+=timedelta(days=1)
    session.flush()
