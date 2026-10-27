import json
from pathlib import Path
from lottery.predict import generate_tickets
from lottery.prospective import versions
from test_api import api
from test_workflow import draw
from lottery.ingestion import ingest
from sqlalchemy.orm import Session

BASELINE=json.loads((Path(__file__).parent/'fixtures/behavior-v1.json').read_text())

def test_frozen_ticket_and_model_identity_baseline():
    for game,tickets in BASELINE['tickets'].items():
        assert generate_tickets(game,BASELINE['seed'])==tickets
    from lottery.experiment_registry import registered_versions, LEGACY_SELECTION
    assert registered_versions(LEGACY_SELECTION)==BASELINE['versions']
    assert all(v!=BASELINE['versions'][k] for k,v in versions().items())


def test_draw_api_compatible_response(api):
    client,engine=api
    with Session(engine) as session:
        ingest(session,draw(),None,'cwl');session.commit()
    actual=client.get('/api/draws?game=ssq').json()
    actual['items'][0]['updated_at']='<timestamp>'
    expected=json.loads((Path(__file__).parent/'fixtures/draw-api-v1.json').read_text())
    assert actual==expected


def test_generation_change_cannot_reuse_legacy_identity(monkeypatch):
    from lottery import experiments
    from lottery.generation_versions import registered_versions
    monkeypatch.setitem(experiments.PROTOCOL,'seed',20261027)
    changed=registered_versions()
    assert set(changed)==set(BASELINE['versions'])
    assert all(changed[k]!=BASELINE['versions'][k] for k in changed)
