from lottery import experiment_registry as registry
from lottery.generation_versions import LEGACY_VERSIONS


def test_baseline_registry_retains_old_ids():
    legacy=registry.registered_versions(registry.LEGACY_SELECTION)
    assert {k:legacy[k] for k in LEGACY_VERSIONS}==LEGACY_VERSIONS
    assert all(v!=LEGACY_VERSIONS[k] for k,v in registry.registered_versions().items() if k in LEGACY_VERSIONS)
    descriptor=registry.describe('forest_all')
    assert descriptor['config']['training_window']==300
    assert descriptor['components']['estimator']
    assert descriptor['feature_groups'] and descriptor['environment']


def test_new_boost_and_blend_have_separate_versions():
    versions=registry.registered_versions()
    assert versions['boost_all'].startswith('boost_all-v2-')
    assert versions['ensemble_all'].startswith('ensemble_all-v2-')


def test_ast_ignores_comments_docstrings_and_location():
    assert registry.source_digest('def f(x):\n    "doc"\n    return x+1\n')==registry.source_digest('\n# moved\ndef f(x):\n    "changed"\n    return x + 1\n')
    assert registry.source_digest('def f(x):\n    return x+1')!=registry.source_digest('def f(x):\n    return x+2')


def test_forest_only_change_does_not_reset_other_models(monkeypatch):
    from lottery import model_training
    before=registry.registered_versions()
    def different(seed): return None
    monkeypatch.setattr(model_training,'forest_estimator',different)
    after=registry.registered_versions()
    assert after['forest_all']!=before['forest_all']
    assert all(after[k]==before[k] for k in before if k!='forest_all')


def test_unrelated_protocol_description_does_not_reset(monkeypatch):
    from lottery.experiments import PROTOCOL
    before=registry.registered_versions()
    monkeypatch.setitem(PROTOCOL,'promotion','clarified documentation')
    assert registry.registered_versions()==before


def test_feature_change_is_scoped(monkeypatch):
    from lottery import indicators
    before=registry.registered_versions()
    monkeypatch.setitem(indicators.STRATEGIES,'freq_odd',('odd','size'))
    after=registry.registered_versions()
    assert after['freq_odd']!=before['freq_odd']
    assert all(after[k]==before[k] for k in before if k!='freq_odd')


def test_new_identity_fits_existing_database_column(monkeypatch):
    from lottery.experiments import PROTOCOL
    monkeypatch.setitem(PROTOCOL,'seed',20261027)
    assert all(len(version)<=60 for version in registry.registered_versions().values())


def test_evidence_protocol_change_cannot_inherit_identity(monkeypatch):
    before=registry.registered_versions()
    monkeypatch.setattr(registry,'EVIDENCE_PROTOCOL','prospective-e-v2')
    assert all(v!=before[k] for k,v in registry.registered_versions().items())


def test_unrelated_model_change_does_not_block_artifact_replay(tmp_path,monkeypatch):
    from lottery import model_training as training
    from lottery.model_artifacts import save_model,load_model
    from lottery.predict import generate_tickets
    model=training.fit_model('ssq',[generate_tickets('ssq',i,1)[0] for i in range(160)],'frequency')
    ref=save_model(model,tmp_path)
    def changed(seed): return None
    monkeypatch.setattr(training,'forest_estimator',changed)
    assert training.predict_model(load_model(ref['id'],tmp_path))==training.predict_model(model)


def test_scoring_change_gets_new_evidence_identity(monkeypatch):
    from lottery import prospective
    before=registry.registered_versions()
    monkeypatch.setattr(prospective,'MIN_SAMPLES',61)
    assert all(v!=before[k] for k,v in registry.registered_versions().items())


def test_failed_forecast_also_keeps_recipe(session):
    from datetime import datetime
    from sqlalchemy import select
    from lottery.models import CandidateForecast
    from lottery.ingestion import ingest
    from lottery.workflow import persist_prediction
    from lottery.domain import TZ
    from test_workflow import draw
    ingest(session,draw(),None,'cwl')
    persist_prediction(session,'ssq',datetime(2026,10,23,8,tzinfo=TZ))
    for forecast in session.scalars(select(CandidateForecast)):
        assert forecast.error
        assert forecast.provenance['experiment_hash']==registry.fingerprint(forecast.model)
        assert forecast.provenance['experiment']==registry.describe(forecast.model)


from test_prospective import session


import pytest

@pytest.mark.parametrize('function',['status','choose','select_strategy'])
def test_evidence_aggregation_and_promotion_changes_get_new_identity(monkeypatch,function):
    from lottery import prospective
    before=registry.registered_versions()
    def changed_policy(*args): return None
    monkeypatch.setattr(prospective,function,changed_policy)
    assert all(v!=before[k] for k,v in registry.registered_versions().items())
