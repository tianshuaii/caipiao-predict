import json
from lottery.db import session_factory
from lottery.collectors import collect_archive
from lottery.ingestion import coverage
from lottery.models import Run, utcnow

with session_factory()() as session:
    run=Run(kind='history',details={'game':'ssq','source':'zhcw'})
    session.add(run)
    session.commit()
    try:
        result=collect_archive(session)
        run.details={**result,'coverage':coverage(session,'ssq')}
        run.status='success' if run.details['coverage']['complete'] else 'partial'
    except Exception as exc:
        session.rollback()
        run.status='failed'
        run.details={'error':str(exc)[:250]}
    run.finished_at=utcnow()
    session.commit()
    print(json.dumps(run.details,ensure_ascii=False))
