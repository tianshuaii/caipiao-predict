"""Populate official history, with one independent transaction stream per game."""
from concurrent.futures import ThreadPoolExecutor
import json
from lottery.db import session_factory
from lottery.collectors import collect
from lottery.ingestion import coverage
from lottery.models import Run, utcnow

def sync(game):
    with session_factory()() as session:
        run = Run(kind='history', details={'game': game})
        session.add(run)
        session.commit()
        try:
            detail = collect(session, game, full=True)
            detail['coverage'] = coverage(session, game)
            run.details = detail
            run.status = 'success' if detail['coverage']['complete'] else 'partial'
        except Exception as exc:
            session.rollback()
            run.status = 'failed'
            run.details = {'game': game, 'error': str(exc)[:250]}
        run.finished_at = utcnow()
        session.commit()
        return run.details

if __name__ == '__main__':
    for result in ThreadPoolExecutor(2).map(sync, ['dlt','ssq']):
        print(json.dumps(result, ensure_ascii=False), flush=True)
