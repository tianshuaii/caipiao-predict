import pytest
from lottery.simulation import run_simulation


def config(**kw):
    return {'ticket':{'game':'ssq','kind':'single','front':[1,2,3,4,5,6],'back':[1]},'start_issue':'2025001','periods':3,'initial_balance':'10','budget':'10',**kw}


def snapshots(amount='0'):
    return [{'data':{'issue':f'2025{i:03d}','front':[8,9,10,11,12,13],'back':[2],'prizes':{}},'conflict':False,'fingerprint':str(i)} for i in range(1,4)]


def test_balance_budget_and_loss_stops():
    r=run_simulation(config(initial_balance='3'),snapshots())
    assert r['stop_reason']=='insufficient_balance' and r['balance']=='1' and r['spent']=='2'
    assert run_simulation(config(budget='3'),snapshots())['stop_reason']=='budget_limit'
    r=run_simulation(config(stop_loss='3'),snapshots())
    assert r['stop_reason']=='loss_limit' and r['played']==1
    r=run_simulation(config(),snapshots())
    assert r['stop_reason']=='period_limit' and r['balance']=='4' and len(r['ledger'])==7


def test_missing_conflict_pending_and_win():
    rows=snapshots()
    assert run_simulation(config(),rows[1:])['stop_reason']=='missing_draw'
    rows[1]['conflict']=True
    assert run_simulation(config(),rows)['played']==1
    rows=snapshots();rows[0]['data']['back']=[1]
    r=run_simulation(config(),rows)
    assert r['stop_reason']=='amount_pending' and r['net'] is None and r['balance']=='8'
    rows[0]['data']['prizes']={'6':{'amount':'5'}}
    r=run_simulation(config(stop_on_win=True),rows)
    assert r['stop_reason']=='win' and r['balance']=='13' and r['net']=='3'

from test_api import api
from test_auth import configured,login,ORIGIN
from sqlalchemy.orm import Session
from lottery.models import SimulationRun


def test_auth_snapshot_replay_and_integrity(api,configured):
    client,engine=api
    assert client.post('/api/simulations',json=config()).status_code==401
    token=login(client).json()['csrf_token']
    response=client.post('/api/simulations',headers={**ORIGIN,'X-CSRF-Token':token},json=config())
    assert response.status_code==201
    id=response.json()['id']
    assert client.get(f'/api/simulations/{id}?replay=true').json()['matches']
    assert client.get('/api/simulations').json()['total']==1
    with Session(engine) as s:
        row=s.get(SimulationRun,id);row.config={**row.config,'budget':'1'};s.commit()
    assert not client.get(f'/api/simulations/{id}?replay=true').json()['matches']
    with Session(engine) as s:
        row=s.get(SimulationRun,id);row.snapshot_hash='broken';s.commit()
    assert client.get(f'/api/simulations/{id}?replay=true').status_code==409


@pytest.mark.parametrize('change',[{'periods':0},{'periods':31},{'initial_balance':'NaN'},{'budget':'-1'},{'stop_loss':'0'},{'start_issue':'2025000'}])
def test_invalid_configs(change):
    with pytest.raises(ValueError):run_simulation(config(**change),[])


def test_snapshot_unchanged_and_bounded():
    import copy
    rows=snapshots();old=copy.deepcopy(rows)
    assert run_simulation(config(),rows)==run_simulation(config(),rows)
    assert old==rows
    c=config(periods=30);c['ticket']={'game':'ssq','kind':'multiple','front':list(range(1,13)),'back':[1,2]}
    with pytest.raises(ValueError,match='20000'):run_simulation(c,[])


def test_migration_preserves_existing_tables(tmp_path,monkeypatch):
    from pathlib import Path
    from sqlalchemy import create_engine,inspect
    from alembic import command
    from alembic.config import Config
    from lottery.models import Base,Draw
    from lottery.ingestion import ingest
    from test_workflow import draw
    import lottery.db as db
    engine=create_engine('sqlite:///'+str(tmp_path/'simulation.db'))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='simulation_runs'])
    with Session(engine) as s:ingest(s,draw(),None,'cwl');s.commit()
    monkeypatch.setattr(db,'engine',lambda:engine)
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(cfg,'007');command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    assert 'simulation_runs' in inspect(engine).get_table_names()
    with Session(engine) as s:assert s.query(Draw).count()==1


def test_year_boundary_version_and_source_revision(api):
    from lottery.simulation import create_simulation,SimulationConfig,replay
    from lottery.ingestion import ingest
    from lottery.models import Draw
    from test_workflow import draw
    rows=snapshots();rows[1]['data']['issue']='2026001'
    assert run_simulation(config(),rows)['stop_reason']=='year_boundary'
    _,engine=api
    with Session(engine) as s:
        ingest(s,draw(),None,'cwl');s.commit()
        row=create_simulation(s,SimulationConfig.model_validate(config(start_issue='2026121')))
        original=row.result
        source=s.query(Draw).first();source.data={**source.data,'back':[16]};s.commit()
        assert replay(row)['matches'] and row.result==original
        row.version='future-version'
        with pytest.raises(ValueError,match='版本'):replay(row)
