# Crypto ↔ IDX Architectural Parity Audit

## Safety (confirmed)
- LIVE_EXECUTION=false
- BROKER_EXECUTION=false
- PAPER_ONLY=true
- AUTO_PROMOTION=false
- IDX_CORE_FROZEN=true
- CRYPTO_LEDGER_SEPARATE=true
- CRYPTO_EXECUTION_POLICY=NEXT_BAR_OPEN
- EXECUTION_RESOLVER_SINGLE_SSOT=true
- SHADOW_AUTO_PAPER=false
- Momentum shadow remains REJECTED → KEEP_SHADOW_RESEARCH

## Added
- governor.py, execution_gate.py, signal_contract.py, cycle.py, data_quality.py
- tests/test_crypto_ops_parity.py

## Modified (crypto only)
- config.py, risk.py, signal_bot.py

## Pipeline
FeatureSnapshot → Signal → Risk → Governor → Execution Gate → NEXT_BAR_OPEN → USDT Ledger

## Tests
60 crypto tests PASS
