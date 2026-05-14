# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This is **PolyRD** — a specialization of Microsoft's RD-Agent framework for [Polymarket](https://polymarket.com), the on-chain prediction market. The goal is to autonomously discover, implement, validate, and evolve **alpha factors** for specific Polymarket market categories (e.g., politics, sports, crypto, economics), ultimately feeding the best factors into a live trading bot.

The R&D loop adapted for Polymarket:
1. **Research**: hypothesize a new factor or signal for a category (e.g., "implied probability momentum over 24h in crypto markets")
2. **Development**: implement the factor as executable Python against Polymarket data
3. **Evaluation**: backtest against historical Polymarket CLOB data using per-category validation metrics
4. **Feedback**: feed IC, calibration, and win-rate results back into hypothesis generation

## Development Setup

```bash
# Install all dev dependencies and pre-commit hooks (Python 3.10 or 3.11)
cd RD-Agent
make dev
```

Configuration is loaded from a `.env` file in `RD-Agent/`. Copy `RD-Agent/.env.example` to `RD-Agent/.env` and fill in at minimum `CHAT_MODEL`, `EMBEDDING_MODEL`, and the corresponding API keys. Run `rdagent health_check` to validate the LLM setup.

## Common Commands

All `make` and `pytest` commands run from inside `RD-Agent/` unless noted.

```bash
# Lint (mypy + ruff + isort + black + toml-sort)
cd RD-Agent && make lint

# Auto-fix most lint issues
cd RD-Agent && make auto-lint

# Run tests (requires API access)
cd RD-Agent && make test

# Run offline-only tests (no external API calls)
cd RD-Agent && make test-offline

# Run a single test file
conda run -n quantaalpha python -m pytest RD-Agent/test/path/to/test_file.py -s

# Run Polymarket-specific tests
conda run -n quantaalpha python -m pytest RD-Agent/test/polymarket/ -s -m offline

# Launch the Streamlit trace viewer
rdagent ui --port 19899 --log-dir RD-Agent/log/
```

Line length is 120. Import order is `isort` with the `black` profile. mypy is enforced only on `rdagent/core/`.

## Polymarket Scenario — Where to Build

All Polymarket-specific code lives under the scenario + app pattern established by the framework:

```
RD-Agent/rdagent/scenarios/polymarket/     # Polymarket scenario (mirrors qlib/ structure)
    scen.py                                # PolymarketScenario (extends Scenario)
    conf.py                               # PolymarketConf (BaseSettings, reads from .env)
    factor/
        exp.py                            # PolymarketFactorTask, PolymarketFactorExperiment
        eval.py                           # Evaluator: IC, calibration, win-rate by category
        prompts.yaml                      # Factor proposal/coding prompts
    data/
        loader.py                         # Polymarket data fetcher (REST + CLOB WebSocket)
        schema.py                         # Typed dataclasses for market events, CLOB snapshots
        cache.py                          # Local parquet cache for historical data

RD-Agent/rdagent/app/polymarket/
    conf.py                               # CLI-level config (extends PolymarketConf)
    loop.py                               # LoopBase subclass: propose → code → evaluate → feedback

RD-Agent/test/polymarket/
    test_data_loader.py                   # Offline: schema validation, mock API responses
    test_factor_eval.py                   # Offline: metric correctness on synthetic data
    test_loop.py                          # Online: full R&D loop smoke test
```

Register new CLI commands in `RD-Agent/rdagent/app/cli.py` following the existing pattern.

## Polymarket Data

### Sources

- **Gamma Markets API** (`https://gamma-api.polymarket.com`) — market metadata, categories, descriptions, resolution criteria, closing prices
- **CLOB API** (`https://clob.polymarket.com`) — order book snapshots, trade history, mid-price time series per token
- **Polymarket API** (`https://api.polymarket.com`) — portfolio, positions, event metadata

### Data Model

Each Polymarket market resolves to YES (1.0) or NO (0.0). Markets are grouped into **events** (e.g., "2024 US Election") with one or more outcome tokens. Key fields to capture per market:

| Field | Description |
|---|---|
| `market_id` | CLOB token ID (YES token address) |
| `event_id` | Parent event grouping markets |
| `category` | e.g., `politics`, `sports`, `crypto`, `economics`, `science` |
| `end_date` | UTC resolution timestamp |
| `mid_price` | Implied probability (0–1 USDC per share) |
| `volume_24h` | Trading volume in USDC over 24h |
| `spread` | Best ask – best bid |
| `liquidity` | Sum of resting orders within 5% of mid |
| `outcome` | Final resolution value (1.0 / 0.0 / NaN if unresolved) |

Store snapshots as parquet files partitioned by `category/date`. The data loader must handle pagination, rate limits, and market delistings gracefully.

### Environment Variables for Data

```bash
POLY_API_KEY=<your_polymarket_api_key>                  # For authenticated endpoints
POLY_CLOB_HOST=https://clob.polymarket.com
POLY_GAMMA_HOST=https://gamma-api.polymarket.com
POLY_DATA_PATH=./RD-Agent/git_ignore_folder/poly_data   # Local parquet cache root
POLY_HISTORY_START=2023-01-01                           # How far back to fetch
```

## Factor Design

### Factor Taxonomy

Factors should be developed and evaluated **per category** — a factor strong in `crypto` markets may be noise in `politics`. Each factor implementation is a Python function:

```python
def compute(market_df: pd.DataFrame, snapshot_df: pd.DataFrame) -> pd.Series:
    """
    Returns a float signal aligned to market_id index.
    Higher = more likely YES, lower = more likely NO.
    """
```

### Factor Categories to Explore

- **Momentum / mean-reversion**: mid-price velocity, RSI-style oscillators on implied probability
- **Liquidity signals**: spread compression, order book depth changes, volume spikes
- **Time-decay**: days-to-resolution, overnight probability drift
- **Category-specific**: e.g., for `politics` — poll release timing, incumbent bias; for `crypto` — spot price correlation
- **Cross-market**: related market correlation, implied basket arbitrage
- **Resolution bias**: historical over/under-pricing by market maker for similar past events

### Factor Variables (analogues to qlib alpha158)

Define a canonical variable set for Polymarket (e.g., `ALPHA_POLY`) covering rolling windows on: `mid`, `spread`, `volume`, `depth_5pct`, `num_trades`, `days_to_end`. New factor hypotheses should reference these primitives wherever possible to keep evaluation comparable.

## Validation & Evaluation

### Metrics (per category, per factor)

| Metric | Definition | Target |
|---|---|---|
| **IC** | Pearson correlation of factor rank vs. resolution outcome | > 0.05 |
| **ICIR** | IC / std(IC) across rolling windows | > 0.5 |
| **Calibration** | Brier score of factor-implied prob vs. outcome | < 0.20 |
| **Win Rate** | % of positions factor would take that resolve correctly | > 55% |
| **Edge** | Expected value per trade = (win_rate × avg_win) – (lose_rate × avg_loss) | > 0 |

### Validation Protocol

1. **Hold-out split**: train on markets resolved before 6 months ago, validate on the last 6 months
2. **Category-stratified**: report metrics separately per category; never aggregate across categories to mask poor performance
3. **Liquidity filter**: only evaluate on markets with `volume_24h > $500` and `spread < 0.05` — thin markets produce noisy labels
4. **Resolution leakage check**: ensure no factor uses data timestamped after `end_date - 1h`

### Test Requirements

- All factor implementations must pass `RD-Agent/test/polymarket/test_factor_eval.py` in offline mode (synthetic market data, known outcomes)
- Data loaders must pass schema validation tests that can run without API keys
- The full R&D loop must complete at least one iteration in smoke tests with a mocked LLM

## RD-Agent Base Architecture (Reference)

The framework below is inherited unchanged. Build on top of it, do not modify core abstractions.

| Layer | Path | Role |
|---|---|---|
| **core** | `RD-Agent/rdagent/core/` | Abstract base classes: `Scenario`, `Hypothesis`, `Task`, `Experiment`, `Developer`, `Evaluator`, `KnowledgeBase` |
| **components** | `RD-Agent/rdagent/components/` | Reusable implementations: `CoSTEER` evolving coder, `proposal/`, `runner/`, `document_reader/`, `agent/` (RAG, MCP) |
| **scenarios** | `RD-Agent/rdagent/scenarios/` | Scenario-specific code. Add `polymarket/` here. |
| **app** | `RD-Agent/rdagent/app/` | CLI entry points. Add `polymarket/` here. |

### Key abstractions

- **`LoopBase`** (`RD-Agent/rdagent/utils/workflow/loop.py`) — drives the R→D→evaluate→feedback cycle. Each public method becomes a named step; state is pickle-serialized for resume.
- **`CoSTEER`** (`RD-Agent/rdagent/components/coder/CoSTEER/`) — evolving code generator with RAG-based knowledge injection. Use this for factor code generation.
- **`conf.py` pattern** — each module has a `conf.py` with a Pydantic `BaseSettings` subclass; values come from `.env`.
- **`prompts.yaml`** — prompt templates co-located with the module that uses them.

### LLM backend

All LLM calls go through `RD-Agent/rdagent/oai/`, which wraps LiteLLM. Configure via `RD-Agent/.env`:

```bash
CHAT_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=<key>
```

## File Naming Conventions

- `conf.py` — Pydantic `BaseSettings` subclass for this module's configuration
- `loop.py` — `LoopBase` subclass connecting R and D for a scenario
- `eval.py` / `evaluators.py` — evaluation and metric computation
- `exp.py` — `Task` and `Experiment` subclasses for this scenario
- `loader.py` — data fetching and caching
- `schema.py` — typed data models for external API responses
