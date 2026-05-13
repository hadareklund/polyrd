# PolyRD — Build Plan

Specializing [RD-Agent](https://github.com/microsoft/RD-Agent) for [Polymarket](https://polymarket.com) prediction markets. The goal is to autonomously discover, implement, validate, and evolve alpha factors per market category, feeding the best signals into a live trading bot.

---

## Phase 0 — Foundation
**Goal:** One working end-to-end R&D loop with real Polymarket data.

- [ ] `rdagent/scenarios/polymarket/data/schema.py` — typed dataclasses for Gamma API markets, CLOB trade history, order book snapshots
- [ ] `rdagent/scenarios/polymarket/data/loader.py` — paginated fetch from Gamma + CLOB REST APIs, parquet cache partitioned by `category/date`
- [ ] `rdagent/scenarios/polymarket/data/cache.py` — read/write helpers, staleness checks, offline fallback
- [ ] `test/polymarket/test_data_loader.py` — schema validation against mock responses (offline, no API key needed)
- [ ] `rdagent/scenarios/polymarket/conf.py` — `PolymarketConf(BaseSettings)` for API keys, data paths, category filter
- [ ] `rdagent/scenarios/polymarket/scen.py` — `PolymarketScenario(Scenario)`
- [ ] `rdagent/scenarios/polymarket/factor/exp.py` — `PolymarketFactorTask`, `PolymarketFactorExperiment`
- [ ] `rdagent/scenarios/polymarket/factor/eval.py` — IC, ICIR, Brier score, win rate per category with liquidity filter
- [ ] `rdagent/app/polymarket/loop.py` — `PolymarketFactorLoop(LoopBase)`: propose → code → run → evaluate → feedback
- [ ] `rdagent/app/polymarket/factor.py` + register `rdagent poly_factor` in `rdagent/app/cli.py`

## Phase 1 — Factor Library Bootstrap
**Goal:** 10–20 hand-crafted baseline factors to seed the LLM knowledge base.

- [ ] Define `ALPHA_POLY` variable set: rolling windows (1h, 4h, 24h, 7d) on `mid`, `spread`, `volume`, `depth_5pct`, `num_trades`, `days_to_end`
- [ ] Implement baselines: mid-price momentum, spread compression, volume surge, time-decay, resolution bias by category
- [ ] Run each through the evaluator to establish IC/ICIR benchmarks per category
- [ ] Store results in CoSTEER knowledge base

## Phase 2 — Autonomous R&D Loop
**Goal:** LLM agent discovers factors the baselines miss.

- [ ] Wire `PolymarketFactorLoop` to CoSTEER for code generation
- [ ] Tune `prompts.yaml` with prediction market mechanics, resolution criteria, CLOB semantics
- [ ] Run multi-category sweeps: `politics`, `crypto`, `sports`, `economics` as separate evaluation buckets
- [ ] Persist winning factors to a catalog with metadata (IC, category, window, feature dependencies)

## Phase 3 — Validation Hardening
**Goal:** Nothing ships to the trading bot that is data-leaky or overfit.

- [ ] Walk-forward validation: top factors evaluated on rolling 30-day out-of-sample windows
- [ ] Cross-category transfer test: flag factors that only work in one category (fragility signal)
- [ ] Leakage scanner: static analysis ensuring no factor reads data within 1h of `end_date`
- [ ] Factor correlation matrix: prune factors with |ρ| > 0.8 to one representative

## Phase 4 — Trading Bot Interface
**Goal:** Validated factor library exposed as a live signal feed.

- [ ] `rdagent/scenarios/polymarket/signal/` — real-time signal computation from live CLOB snapshots
- [ ] Factor ensemble: ICIR-weighted combination per category
- [ ] REST or WebSocket endpoint serving current signal scores per open market
- [ ] Position sizing: Kelly-fraction sizing based on edge estimate
