import pytest
from test_api import api
from lottery.api import app

# A future write route must be guarded by the application's global dependency.
@app.post('/api/test-admin-write',include_in_schema=False)
def protected_probe():return {'ok':True}

ORIGIN={'Origin':'http://127.0.0.1:9998'}

@pytest.fixture
def configured(monkeypatch):
    from lottery.auth import password_hash
    monkeypatch.setenv('ADMIN_USERNAME','operator')
    monkeypatch.setenv('ADMIN_PASSWORD_HASH',password_hash('a-long-test-password'))
    monkeypatch.setenv('ADMIN_ORIGIN','http://127.0.0.1:9998')


def login(client):
    return client.post('/api/auth/login',headers=ORIGIN,json={'username':'operator','password':'a-long-test-password'})


def test_public_read_and_default_denial(api,monkeypatch):
    client,_=api
    monkeypatch.delenv('ADMIN_PASSWORD_HASH',raising=False)
    assert client.get('/api/draws').status_code==200
    assert client.post('/api/test-admin-write',headers=ORIGIN).status_code==401
    assert login(client).status_code==503


def test_login_csrf_logout_and_rotation(api,configured,monkeypatch):
    client,_=api
    assert client.post('/api/auth/login',json={'username':'operator','password':'a-long-test-password'}).status_code==403
    response=login(client);assert response.status_code==200
    assert 'httponly' in response.headers['set-cookie'].lower()
    raw=client.cookies.get('lottery_admin')
    csrf=response.json()['csrf_token'];headers={**ORIGIN,'X-CSRF-Token':csrf}
    assert client.post('/api/test-admin-write',headers=ORIGIN).status_code==403
    assert client.post('/api/test-admin-write',headers={**headers,'Origin':'https://evil.invalid'}).status_code==403
    assert client.post('/api/test-admin-write',headers=headers).status_code==200
    assert client.get('/api/auth/session').json()['authenticated']
    assert client.post('/api/auth/logout',headers=headers).status_code==200
    assert client.post('/api/test-admin-write',headers={**headers,'Cookie':'lottery_admin='+raw}).status_code==401
    login(client);monkeypatch.setenv('ADMIN_PASSWORD_HASH','')
    assert not client.get('/api/auth/session').json()['authenticated']


def test_expiry_and_hashed_storage(api,configured):
    from datetime import datetime,timedelta,timezone
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from lottery.models import AdminSession
    client,engine=api
    response=login(client)
    with Session(engine) as s:
        row=s.scalar(select(AdminSession))
        assert row.token_hash!=client.cookies.get('lottery_admin')
        row.expires_at=datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=1);s.commit()
    assert not client.get('/api/auth/session').json()['authenticated']
    assert client.post('/api/test-admin-write',headers={**ORIGIN,'X-CSRF-Token':response.json()['csrf_token']}).status_code==401


def test_bad_password_and_rate_limit(api,configured):
    client,_=api
    for _ in range(10):
        assert client.post('/api/auth/login',headers=ORIGIN,json={'username':'operator','password':'bad'}).status_code==401
    assert login(client).status_code==429


def test_secure_origin_configuration(api,configured,monkeypatch):
    from lottery.auth import settings
    client,_=api
    monkeypatch.setenv('ADMIN_ORIGIN','http://public.example')
    assert settings() is None
    monkeypatch.setenv('ADMIN_ORIGIN','http://[')
    assert settings() is None
    monkeypatch.setenv('ADMIN_ORIGIN','https://public.example')
    response=client.post('/api/auth/login',headers={'Origin':'https://public.example'},json={'username':'operator','password':'a-long-test-password'})
    assert response.status_code==200 and '; Secure' in response.headers['set-cookie']


def test_auth_migration_preserves_draws(tmp_path,monkeypatch):
    from pathlib import Path
    from sqlalchemy import create_engine,inspect,select,func
    from sqlalchemy.orm import Session
    from alembic import command
    from alembic.config import Config
    from lottery.models import Base,Draw
    from lottery.ingestion import ingest
    from test_workflow import draw
    import lottery.db as db
    engine=create_engine('sqlite:///'+str(tmp_path/'auth.db'))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in {'admin_sessions','login_throttles'}])
    with Session(engine) as s:ingest(s,draw(),None,'cwl');s.commit()
    monkeypatch.setattr(db,'engine',lambda:engine)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    command.stamp(config,'005');command.upgrade(config,'head');command.upgrade(config,'head')
    assert {'admin_sessions','login_throttles'}<=set(inspect(engine).get_table_names())
    with Session(engine) as s:assert s.scalar(select(func.count()).select_from(Draw))==1
