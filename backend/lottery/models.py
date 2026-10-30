from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import DeclarativeBase

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Base(DeclarativeBase):
    pass

class RawFetch(Base):
    __tablename__ = 'raw_fetches'
    id = Column(Integer, primary_key=True)
    source = Column(String(40), nullable=False)
    url = Column(Text, nullable=False)
    params = Column(JSON, nullable=False, default=dict)
    fetched_at = Column(DateTime, default=utcnow, nullable=False)
    status = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    body = Column(Text().with_variant(LONGTEXT(), 'mysql'), nullable=False)
    parser_version = Column(String(30), default='v1', nullable=False)

class Draw(Base):
    __tablename__ = 'draws'
    __table_args__ = (UniqueConstraint('game', 'issue', name='uq_draw_game_issue'),)
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False, index=True)
    issue = Column(String(7), nullable=False, index=True)
    draw_date = Column(Date, nullable=False)
    data = Column(JSON, nullable=False)
    fingerprint = Column(String(64), nullable=False)
    source = Column(String(40), nullable=False)
    raw_id = Column(Integer, ForeignKey('raw_fetches.id'))
    revision = Column(Integer, nullable=False, default=1)
    conflict = Column(Boolean, nullable=False, default=False)
    sources = Column(JSON, nullable=False, default=list)
    updated_at = Column(DateTime, nullable=False, default=utcnow)

class Observation(Base):
    __tablename__ = 'draw_observations'
    __table_args__ = (Index('ix_observations_draw_created','draw_id','created_at'),)
    id = Column(Integer, primary_key=True)
    draw_id = Column(Integer, ForeignKey('draws.id'), nullable=False, index=True)
    raw_id = Column(Integer, ForeignKey('raw_fetches.id'))
    source = Column(String(40), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    data = Column(JSON, nullable=False)
    conflict = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

class Prediction(Base):
    __tablename__ = 'predictions'
    __table_args__ = (UniqueConstraint('game', 'issue', name='uq_prediction_game_issue'),)
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False, index=True)
    issue = Column(String(7), nullable=False)
    draw_date = Column(Date, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    cutoff_issue = Column(String(7), nullable=False)
    strategy = Column(String(60), nullable=False)
    seed = Column(String(30), nullable=False)
    tickets = Column(JSON, nullable=False)
    provenance = Column(JSON, nullable=False)
    dataset_hash = Column(String(64), nullable=False)
    snapshot_path = Column(String(200), nullable=False)
    probabilities = Column(JSON, nullable=False)

class Settlement(Base):
    __tablename__ = 'settlements'
    __table_args__ = (UniqueConstraint('prediction_id', 'draw_fingerprint', name='uq_settlement_revision'),)
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('predictions.id'), nullable=False, index=True)
    draw_fingerprint = Column(String(64), nullable=False)
    results = Column(JSON, nullable=False)
    summary = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

class Run(Base):
    __tablename__ = 'runs'
    id = Column(Integer, primary_key=True)
    kind = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False, default='running')
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime)
    details = Column(JSON, nullable=False, default=dict)

class Notification(Base):
    __tablename__ = 'notifications'
    id = Column(Integer, primary_key=True)
    report_key = Column(String(64), nullable=False, unique=True)
    run_id = Column(Integer, ForeignKey('runs.id'), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default='pending')
    attempts = Column(Integer, nullable=False, default=0)
    detail = Column(String(200))
    created_at = Column(DateTime, nullable=False, default=utcnow)
    sent_at = Column(DateTime)

class Experiment(Base):
    __tablename__ = 'experiments'
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    result = Column(JSON, nullable=False)

class CalendarOverride(Base):
    __tablename__ = 'calendar_overrides'
    __table_args__ = (UniqueConstraint('game', 'day', name='uq_calendar_game_day'),)
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False)
    day = Column(Date, nullable=False)
    closed = Column(Boolean, nullable=False, default=True)
    source_url = Column(Text, nullable=False)
    note = Column(Text, nullable=False)

class CandidateForecast(Base):
    __tablename__ = 'candidate_forecasts'
    __table_args__ = (UniqueConstraint('game', 'issue', 'strategy', name='uq_candidate_issue_strategy'),)
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False, index=True)
    issue = Column(String(7), nullable=False)
    strategy = Column(String(60), nullable=False)
    model = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    cutoff_at = Column(DateTime, nullable=False)
    cutoff_issue = Column(String(7), nullable=False)
    seed = Column(String(30), nullable=False)
    probabilities = Column(JSON, nullable=False, default=dict)
    tickets = Column(JSON, nullable=False, default=list)
    snapshot_path = Column(String(200), nullable=False)
    dataset_hash = Column(String(64), nullable=False)
    provenance = Column(JSON, nullable=False)
    error = Column(String(200))

class CandidateScore(Base):
    __tablename__ = 'candidate_scores'
    __table_args__ = (UniqueConstraint('forecast_id', 'draw_fingerprint', name='uq_candidate_score_revision'),)
    id = Column(Integer, primary_key=True)
    forecast_id = Column(Integer, ForeignKey('candidate_forecasts.id'), nullable=False, index=True)
    draw_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    metrics = Column(JSON, nullable=False)

class StrategyDecision(Base):
    __tablename__ = 'strategy_decisions'
    __table_args__ = (UniqueConstraint('game', 'evaluation_key', name='uq_strategy_evaluation'),)
    id = Column(Integer, primary_key=True)
    game = Column(String(8), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    evaluation_key = Column(String(64), nullable=False)
    previous = Column(String(60), nullable=False)
    selected = Column(String(60), nullable=False)
    reason = Column(String(200), nullable=False)
    evidence = Column(JSON, nullable=False)

class RandomControl(Base):
    __tablename__ = 'random_controls'
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey('predictions.id'), nullable=False, unique=True)
    game = Column(String(8), nullable=False, index=True)
    issue = Column(String(7), nullable=False)
    created_at = Column(DateTime, nullable=False)
    cutoff_at = Column(DateTime, nullable=False)
    seed = Column(String(30), nullable=False)
    protocol = Column(String(40), nullable=False)
    groups = Column(JSON, nullable=False)

class ControlScore(Base):
    __tablename__ = 'control_scores'
    __table_args__ = (UniqueConstraint('control_id', 'draw_fingerprint', name='uq_control_revision'),)
    id = Column(Integer, primary_key=True)
    control_id = Column(Integer, ForeignKey('random_controls.id'), nullable=False, index=True)
    draw_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    groups = Column(JSON, nullable=False)

class WinnerCase(Base):
    __tablename__ = 'winner_cases'
    id = Column(Integer, primary_key=True)
    case_key = Column(String(64), nullable=False, unique=True)
    game = Column(String(8), nullable=False, index=True)
    issue = Column(String(7), nullable=False, index=True)
    ticket_type = Column(String(20), nullable=False)
    article_url = Column(Text, nullable=False)
    title = Column(String(300), nullable=False)
    source = Column(String(100), nullable=False)
    published_date = Column(Date)
    fetched_at = Column(DateTime, nullable=False, default=utcnow)
    raw_id = Column(Integer, ForeignKey('raw_fetches.id'), nullable=False)
    evidence = Column(Text, nullable=False)
    details = Column(JSON, nullable=False)
    images = Column(JSON, nullable=False)
    status = Column(String(30), nullable=False)
    parser_version = Column(String(30), nullable=False)
    active = Column(Boolean, nullable=False, default=True)

class AdminSession(Base):
    __tablename__ = 'admin_sessions'
    token_hash = Column(String(64), primary_key=True)
    credential_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

class LoginThrottle(Base):
    __tablename__ = 'login_throttles'
    key = Column(String(64), primary_key=True)
    bucket = Column(Integer, nullable=False)
    attempts = Column(Integer, nullable=False)

class ResearchJob(Base):
    __tablename__ = 'research_jobs'
    id = Column(Integer, primary_key=True)
    active_slot = Column(Integer, unique=True, nullable=True)
    status = Column(String(20), nullable=False)
    submitted_by = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    config = Column(JSON, nullable=False)
    snapshot = Column(JSON, nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    recipe_hash = Column(String(64), nullable=True)
    result = Column(JSON)
    error = Column(String(300))

class SimulationRun(Base):
    __tablename__ = 'simulation_runs'
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    version = Column(String(40), nullable=False)
    config = Column(JSON, nullable=False)
    snapshot = Column(JSON, nullable=False)
    snapshot_hash = Column(String(64), nullable=False)
    result = Column(JSON, nullable=False)
    result_hash = Column(String(64), nullable=False)
