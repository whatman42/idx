# IDX Architecture Adoption Matrix

**Constraint plane:** GitHub Actions Free (cheap control) · Google Colab (expensive research) · LLM (reasoning only) · PromotionGate (mandatory) · Paper-only (no live broker)

**Principle:** AI may propose hypotheses and experiments. AI must not auto-mutate Champion.

## Decision vocabulary

| Decision | Meaning |
|----------|---------|
| **ADOPT** | Concept enters IDX runtime/research plane as-is in spirit |
| **ADAPT** | Concept enters, reshaped for EOD + Actions + Colab + paper-only |
| **REFERENCE_ONLY** | Design inspiration; no runtime dependency |
| **REJECT** | Increases complexity/risk without enough value, or violates architecture |

## Matrix

| Repository | Concept | IDX target | Decision | Actions cost | Leakage risk |
|------------|---------|------------|----------|--------------|--------------|
| Qlib | Research workflow, alpha eval, drift | `research.factory`, `learning.drift`, `strategy.evaluator` | ADAPT | LOW | MED |
| RD-Agent | Hypothesis → experiment → evaluate → iterate | `research.factory`, `learning.hypothesis`, `learning.experiment` | ADAPT | LOW | LOW |
| FinRL-X | Modular data/strategy/backtest interfaces | evaluator + Colab jobs | ADAPT | LOW | MED |
| TradingAgents | Analyst / research / risk role split | LLM reasoning plane | ADAPT | NONE | LOW |
| FinRobot / FinGPT | Financial LLM research | LLM reasoning-only | REFERENCE | NONE | LOW |
| FinRL | RL trading | Colab research challenger | ADAPT | HIGH | HIGH |
| vectorbt | Vectorized param/strategy search | Colab hyperopt / sweep jobs | ADAPT | NONE | MED |
| skfolio | Portfolio opt, leakage-aware CV | regime matrix + time-split discipline | ADAPT | LOW | HIGH |
| LEAN / Nautilus | Event-driven state, risk isolation | ops paper path + risk gate principles | REFERENCE | NONE | LOW |
| Freqtrade / Jesse | Hyperopt, practical strategy eng. | Colab hyperopt + experiment ledger | ADAPT | NONE | MED |
| Hummingbot | Strategy/controller/executor split | production_signal + risk + paper_portfolio | REFERENCE | NONE | LOW |
| Full Qlib/LEAN runtime | Vendor entire engine | — | **REJECT** | HIGH | MED |
| Online Champion mutation | Retrain-and-swap every trade | — | **REJECT** | HIGH | HIGH |
| Live / demo / dry-run broker | External order submission | — | **REJECT** | HIGH | LOW |

## Planes

```
Production  → deterministic paper path (Champion only)
Learning    → episode, attribution, failure, drift, meta (advisory)
Research    → factory, regime matrix, Colab jobs, WFA, challengers
Reasoning   → LLM post-mortem / critique (never SSOT)
Governance  → EvidencePackage → PromotionGate → Authority → Champion
```

## Cadence

| Cadence | Plane | Work |
|---------|-------|------|
| Daily (Actions) | Production + Learning | EOD signal, paper fill, episode, attribution, drift |
| Weekly / threshold | Research | Factory batch, Colab job specs |
| Colab session | Research compute | WFA, hyperopt, challenger train |
| Promotion | Governance | EvidencePackage + gate + authority only |

Runtime source of truth: `src/python/research/adoption.py`.
