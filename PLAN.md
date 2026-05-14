# PolyRD — Build Plan

Specializing [RD-Agent](https://github.com/microsoft/RD-Agent) for [Polymarket](https://polymarket.com) prediction markets. The goal is to autonomously discover, implement, validate, and evolve alpha factors per market category, feeding the best signals into a live trading bot.

---

## Phase 0 — Foundation ✓
**Goal:** One working end-to-end R&D loop with real Polymarket data.

- [x] `rdagent/scenarios/polymarket/data/schema.py` — typed dataclasses for Gamma API markets, CLOB trade history, order book snapshots
- [x] `rdagent/scenarios/polymarket/data/loader.py` — paginated fetch from Gamma + CLOB REST APIs, parquet cache partitioned by `category/date`
- [x] `rdagent/scenarios/polymarket/data/cache.py` — read/write helpers, staleness checks, offline fallback
- [x] `test/polymarket/test_data_loader.py` — schema validation against mock responses (28/28 offline tests passing)
- [x] `rdagent/scenarios/polymarket/conf.py` — `PolymarketConf(BaseSettings)` for API keys, data paths, category filter
- [x] `rdagent/scenarios/polymarket/scen.py` — `PolymarketScenario(Scenario)`
- [x] `rdagent/scenarios/polymarket/factor/exp.py` — `PolymarketFactorTask`, `PolymarketFactorExperiment`
- [x] `rdagent/scenarios/polymarket/factor/eval.py` — IC, ICIR, Brier score, win rate per category with liquidity filter
- [x] `rdagent/app/polymarket/loop.py` — `PolymarketFactorRDLoop(RDLoop)`: propose → code → run → evaluate → feedback
- [x] `rdagent poly_factor` registered in `rdagent/app/cli.py` (entry point in `loop.py`; no separate `factor.py` needed)

---

## Phase 1 — Eval Hardening & Primitives
**Goal:** Harden the eval harness with a leakage guard and define the canonical variable set — every future factor runs through this before entering the catalog.

- [ ] `rdagent/scenarios/polymarket/factor/eval.py` — add **leakage guard**: reject any factor that reads snapshot columns timestamped within 1h of `end_date`; static check enforced at eval time before IC is computed
- [ ] `test/polymarket/test_factor_eval.py` — extend existing tests (currently 15/15): add leakage guard assertions (synthetic leaky factor is rejected, clean factor passes); add warning assertion when < 20 markets survive the liquidity filter
- [ ] `rdagent/scenarios/polymarket/data/variables.py` — define `ALPHA_POLY` canonical variable set: `compute_features(market_df, snapshot_df) -> pd.DataFrame` returning rolling windows (1h, 4h, 24h, 7d) on `mid`, `spread`, `volume`, `depth_5pct`, `num_trades`, `days_to_end`; all baseline and LLM-generated factors reference these primitives

**Verify:** `pytest test/polymarket/ -m offline` — all pass; synthetic leaky factor is rejected by the guard.

---

## Phase 2 — Baseline Factor Library
**Goal:** 10–15 hand-crafted factors establish per-category IC/ICIR benchmarks and seed the CoSTEER knowledge base.

Factors are implemented as `compute(market_df, snapshot_df) -> pd.Series` using `ALPHA_POLY` primitives.

- [ ] `rdagent/scenarios/polymarket/factor/baselines/` — one file per factor family:
  - `momentum.py` — mid-price velocity (1h, 4h, 24h), RSI-style oscillator on implied probability
  - `liquidity.py` — spread compression rate, order book depth change, volume surge ratio
  - `time_decay.py` — days-to-resolution decay, overnight drift (open→close delta)
  - `resolution_bias.py` — historical over/under-pricing by category (requires resolved markets in cache)
  - `cross_market.py` — correlation with related market mid-prices at the event level
- [ ] Each baseline validated through `test_factor_eval.py` in offline mode (synthetic data with known outcomes)
- [ ] `rdagent/scenarios/polymarket/factor/catalog.py` — persist each evaluated factor's metadata (name, category, IC, ICIR, Brier, window, feature dependencies, code hash) to `POLY_DATA_PATH/catalog/` as JSON; this catalog is what CoSTEER reads as prior knowledge
- [ ] Run baselines on real data; record per-category IC/ICIR benchmarks in the catalog

**Verify:** Catalog JSON is written with IC/ICIR/Brier populated for all baselines; all baselines pass `test_factor_eval.py`.

---

## Phase 3 — CoSTEER Wiring & Autonomous Loop
**Goal:** LLM agent proposes and implements factors beyond what baselines cover. CoSTEER integration broken into four independently testable steps.

- [ ] `rdagent/scenarios/polymarket/factor/prompts.yaml` — prompts for: (a) factor hypothesis generation grounded in CLOB/Gamma semantics, (b) factor code generation using `ALPHA_POLY` primitives by name, (c) feedback summarization linking IC delta to specific code changes
- [ ] `rdagent/app/polymarket/loop.py` — wire `propose` step to `PolyFactorHypothesisGen` with catalog as context (seed with baseline results before first LLM call)
- [ ] `rdagent/app/polymarket/loop.py` — wire `code` step to `PolyFactorCoSTEER`; sandbox execution via subprocess with 60s timeout; capture stdout/stderr for feedback
- [ ] `rdagent/app/polymarket/loop.py` — wire `evaluate` step: factor runs through `eval.py` (leakage guard + liquidity filter enforced); only IC > 0.05 advances to catalog
- [ ] `rdagent/app/polymarket/loop.py` — wire `feedback` step: serialize IC, ICIR, Brier, win-rate back to knowledge base; prune catalog entries with |ρ| > 0.8 to the existing highest-ICIR representative (correlation matrix updated incrementally)
- [ ] `test/polymarket/test_loop.py` — smoke test: one full propose→code→evaluate→feedback iteration with a mocked LLM (deterministic output); asserts loop completes, catalog is written, leakage guard is exercised
- [ ] Run multi-category sweeps: `politics`, `crypto`, `sports`, `economics` as separate evaluation buckets; target ≥ 3 factors per category with IC > 0.05

**Verify:** `pytest test/polymarket/test_loop.py -m offline` passes; `rdagent poly_factor --step-n 1` completes one live iteration.

---

## Phase 4 — Validation Hardening
**Goal:** Walk-forward and cross-category tests prevent overfitting before any factor touches live capital.

- [ ] `rdagent/scenarios/polymarket/factor/eval.py` — add `walk_forward_validate(factor_fn, catalog_entry)`: evaluates factor on rolling 30-day out-of-sample windows (minimum 3 windows); factor is "validated" only if ICIR > 0.5 in ≥ 2 of 3 windows
- [ ] `rdagent/scenarios/polymarket/factor/eval.py` — add `cross_category_transfer_test(factor_fn)`: runs factor across all categories; flags as "fragile" if IC > 0.05 in only one category
- [ ] `test/polymarket/test_factor_eval.py` — extend with synthetic multi-window data to assert walk-forward logic is correct
- [ ] `rdagent/app/cli.py` — register `rdagent poly_validate`: runs walk-forward + cross-category tests on every catalog entry not yet validated; outputs a report to stdout

**Verify:** `rdagent poly_validate` produces a report with ≥ 1 factor marked validated per category.

---

## Phase 5 — Trading Bot Interface
**Goal:** Validated factors exposed as a live, actionable signal feed.

- [ ] `rdagent/scenarios/polymarket/signal/computer.py` — `SignalComputer`: loads validated catalog entries, fetches live CLOB snapshots via `loader.py`, runs each factor's `compute()`, returns per-market signal scores
- [ ] `rdagent/scenarios/polymarket/signal/ensemble.py` — ICIR-weighted factor ensemble per category; output is a single `[0,1]` signal per open market
- [ ] `rdagent/scenarios/polymarket/signal/sizing.py` — Kelly-fraction position sizing: `f = (p × b - q) / b` capped at 5% of bankroll per position; `b` = avg_win/avg_loss, `p` = win_rate
- [ ] `rdagent/app/polymarket/server.py` — FastAPI app: `GET /signals` (all open markets), `GET /signals/{market_id}`; refreshes on configurable interval (default 5 min); register as `rdagent poly_serve` in `cli.py`
- [ ] `test/polymarket/test_signal.py` — offline tests: mock CLOB snapshots → assert signal scores are in [0,1], ensemble weights sum to 1, Kelly sizing caps at 5%

**Verify:** `rdagent poly_serve` starts; `curl localhost:8000/signals` returns JSON with market scores.

---

## Dependency Order

```
Phase 1 (leakage guard + ALPHA_POLY primitives)
    ↓
Phase 2 (baseline factors + factor catalog)
    ↓
Phase 3 (prompts.yaml + CoSTEER wiring + autonomous loop)
    ↓
Phase 4 (walk-forward + cross-category validation)
    ↓
Phase 5 (signal computer + ensemble + Kelly + FastAPI server)
```

No factor enters Phase 5 without passing Phase 4 validation. Leakage guard (Phase 1) is enforced at every subsequent phase automatically.

---

## Verification Summary

| Phase | Gate |
|---|---|
| 1 | `pytest test/polymarket/ -m offline` — all pass; synthetic leaky factor rejected |
| 2 | Catalog JSON written with IC/ICIR/Brier for all baselines |
| 3 | `pytest test/polymarket/test_loop.py -m offline` passes; one live loop iteration completes |
| 4 | `rdagent poly_validate` produces ≥ 1 validated factor per category |
| 5 | `rdagent poly_serve` starts; `/signals` returns JSON with market scores |
