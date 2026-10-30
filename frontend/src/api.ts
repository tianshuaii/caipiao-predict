export type Game = 'dlt' | 'ssq';
export type Ticket = { front: number[]; back: number[] };
export type Award = { amount: string | null; count: number | null; raw_amount?: string };
export type Draw = Ticket & { id: number; game: Game; issue: string; draw_date: string; sales: string | null; pool: string | null; prizes: Record<string, Award>; source: string; sources: string[]; source_url: string; revision: number; conflict: boolean; updated_at: string; rule_version: string };
export type Settlement = { results: (Ticket & { front_hits: number; back_hits: number; level: number | null; amount: string | null })[]; summary: { pending: number; known_amount: string; amount: string | null; cost: string; net: string | null; winning_tickets: number; rule_version: string }; created_at: string };
export type Prediction = { id: number; game: Game; issue: string; draw_date: string; created_at: string; cutoff_issue: string; strategy: string; seed: string; dataset_hash: string; tickets: Ticket[]; actual: Draw | null; settlement: Settlement | null; provenance: { rationale: string; code_sha256: string; sales_cutoff: string } };
export type Coverage = { count: number; complete: boolean; first_issue: string | null; last_issue: string | null; missing_count: number; conflicts: number; prize_complete_count: number; missing_years?: number[] };
export type Schedule = { label: string; timezone: string; next_run: string; scheduler: { running: boolean; heartbeat?: string } };
export type GameOverview = { name: string; latest: Draw | null; prediction: Prediction | null; coverage: Coverage; recent: Draw[]; frequency: { number: number; count: number }[]; stats: { predictions: number; settled_periods: number; committed_cost: number; settled_cost: number; return: number; net: number; winning_tickets: number } };
export type Overview = { games: Record<Game, GameOverview>; schedule: Schedule; generated_at: string };
export type StrategyMetric = { strategy: string; brier: number | null; mean_hits: number | null; evaluated_periods?: number; failed_periods?: number; cost: number; known_return: number; net: number | null; pending_tickets: number; holm_p: number | null; calibration: { predicted: number; observed: number; count: number }[] };
export type Experiment = { id: number; created_at: string; evaluation_periods: number; from_issue: string; to_issue: string; training_cutoff: string; strategies: StrategyMetric[]; random_simulations: number; random_hit_interval: number[] | null; comparison?: { issues: string[]; excluded: { issue: string; reason: string }[] }; conclusion: string; protocol: { version: string }; dataset_hash: string };
export type Tasks = { runs: { id: number; kind: string; status: string; started_at: string; finished_at: string | null; details: Record<string, unknown> }[]; notifications: { id: number; title: string; status: string; attempts: number; detail: string; created_at: string }[]; schedule: Schedule };

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api' + path, { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `接口暂不可用（${response.status}），请检查后端服务。`);
  }
  return response.json();
}

export type StrategyStatus = {
  portfolio?: PortfolioStatus;
  active: string; minimum_samples: number; minimum_relative_gain: number;
  candidates: { strategy: string; model: string; current_version: boolean; samples: number; forecast_count: number; failed: number; latest_error: string | null; brier: number | null; baseline: number | null; relative_gain: number | null; e_value: number; threshold: number; eligible: boolean }[];
  forecasts: { id: number; issue: string; strategy: string; tickets: Ticket[]; error: string | null; created_at: string; metrics: { brier: number; baseline: number; mean_hits: number; known_return: string; pending: number; cost: number; results: {front_hits: number; back_hits: number; amount: string | null; level: number | null}[] } | null }[];
  decisions: { id: number; previous: string; selected: string; reason: string; created_at: string }[];
};

export type StatisticalInterval = { interval: number[] | null; periods: number; reason?: string | null; block_length?: number; replicates?: number; seed?: number };
export type PortfolioMetric = {
  any_prize_interval?: StatisticalInterval; first_prize_interval?: StatisticalInterval;
  periods: number; any_prize_periods: number; first_prize_periods: number;
  any_prize_rate: number | null; first_prize_rate: number | null;
  cost: number; known_return: string; pending_tickets: number; net: string | null; roi: number | null;
};
export type PortfolioStatus = {
  control_groups: number; protocol: string; note: string;
  rows: { kind: string; strategy: string; rule_version: string; metrics: PortfolioMetric;
    comparison: { random_tracks?: PortfolioMetric[]; random_money_tracks?: PortfolioMetric[]; uncertainty?: { any_prize: StatisticalInterval; first_prize: StatisticalInterval; net_per_period: StatisticalInterval; note: string }; periods: number; money_periods: number; strategy: PortfolioMetric; money_strategy: PortfolioMetric;
      random_any_prize_rate: number[] | null; random_first_prize_rate: number[] | null;
      random_net: number[] | null; random_roi: number[] | null;
    };
  }[];
};

export type WinnerCase = {
  id: number; game: Game; issue: string; ticket_type: string; title: string; article_url: string;
  source: string; published_date: string | null; fetched_at: string; evidence: string;
  images: string[]; status: string; parser_version: string; raw_id: number;
  details: { single_count: number | null; multiplier: number | null; front_count: number | null;
    back_count: number | null; expanded_units: number | null; cost: string | null;
    first_prize_count: number | null; additional: boolean | null; total_prize_text: string | null;
    banker_description: string | null; region: string | null;
  };
};
export type WinnerCases = { items: WinnerCase[]; total: number; limit: number; offset: number; notice: string };

export type RankingObjective = 'brier' | 'any_prize' | 'first_prize' | 'roi';
export type RankingStatus = {
  objective: RankingObjective; minimum_periods: number; participants: string[]; note: string;
  excluded: { strategy: string; issue: string; reason: string }[];
  groups: { rule_version: string; issues: string[]; money_issues: string[];
    excluded: { issue: string; missing_strategies: string[] }[];
    money_excluded: { issue: string; reason: string }[];
    rows: { strategy: string; brier: number | null; metrics: PortfolioMetric; money_metrics: PortfolioMetric;
      value: number | null; periods: number; rank: number | null; reason: string }[];
  }[];
};

export type DataQuality = Coverage & {
  missing: string[]; missing_years?: number[]; inventory_verified?: boolean;
  latest_draw_date: string | null; last_observed_at: string | null; first_observed_at: string | null;
  observation_age_seconds: number | null; prize_complete_rate: number | null;
};
export type DrawDetails = Draw & { observations: {
  source: string; raw_id: number | null; conflict: boolean; created_at: string; data: Draw;
}[] };

export type FeatureCatalog = { version:string; windows:(number|string)[]; note:string;
  features:{id:string;formula:string;null_semantics:string;shape:string}[] };
export type FeatureAnalysis = {
  version:string; as_of:string; cutoff_issue:string; dataset_hash:string; sample_size:number; available_records:number;
  first_issue:string|null; last_issue:string|null; short_window:boolean; notes:string[];
  theory:{number_probability:number;assumption:string};
  numbers:{number:number;count:number;frequency:number|null;current_omission:number|null;left_censored:boolean;
    max_omission:number|null;mean_omission:number|null;completed_intervals:number;hot_rank:number|null;cold_rank:number|null}[];
  distributions:Record<string,{value:number;count:number;frequency:number|null;theoretical_probability:number}[]>;
  combinations:{issue:string;features:Record<string,number|number[]|null>}[];
};

export type ResearchModelCatalog = { models:{id:string;features:string[]}[];windows:number[];max_periods:number;max_budget:number;note:string };
export type ResearchJobConfig = { game:Game;kind:'train'|'backtest';model:string;window:number;periods:number;budget:number;seed:number;issue_to:string };
export type ResearchJob = { duration_seconds?:number|null; id:number;status:string;config:ResearchJobConfig;created_at:string;started_at:string|null;finished_at:string|null;snapshot_hash:string;recipe_hash:string;error:string|null;result?:Record<string,unknown>|null };
