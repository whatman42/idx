# IDX Colab adapter

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/whatman42/idx/blob/main/colab/IDX_GPU_TRAINING.ipynb)

## Roles

| Surface | Role |
|---------|------|
| **GitHub Actions** | Daily operational signals (`rule_sma20` (legacy ops_sma_v0)), paper portfolio |
| **Google Colab** | Heavy / weekend ML **candidate** training & research |
| **Telegram** | Output only |
| **Paper portfolio** | Measurement only (not live trading) |

## Safety

- **No auto-promotion** — Colab never writes the production pointer
- **GPU optional** — full CPU fallback
- **Budget** — `COLAB_TRAINING_BUDGET_SEC` (default **1200**)
- **Economic edge** — remains **UNVERIFIED** until valid forward/OOS evidence
- Paper reset ≠ model/Governor/shadow reset

## How to run

1. Open the badge above (or File → Upload notebook from this folder).
2. Runtime → optional GPU (T4 etc.); CPU is fine.
3. Run all cells top to bottom.
4. Artifacts:
   - `models/candidates/*.joblib` + `*.meta.json`
   - `artifacts/training/last_training_report.json`
   - `artifacts/training/shadow_report.json` (if shadow ran)

## Secrets (optional)

| Secret | Required? |
|--------|-----------|
| `GH_PAT` | Optional — publish reports to GitHub |
| Telegram / Gemini keys | **Not** required for training |

Never put tokens in notebook source.

## Architecture

The notebook is a **thin adapter**. All ML/feature/Governor/shadow logic lives under `src/python/`.

```text
Colab notebook
    → src.python.colab.hardware
    → src.python.colab.run_training
         → Governor.select_models
         → ml.pipeline / features / validation
         → shadow.compare (isolated)
    → optional publish_candidates (GH_PAT)
```
