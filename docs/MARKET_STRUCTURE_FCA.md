# Market Structure & Execution Safety Layer

```
Instrument State + Session State → Price Rules (tick/lot/ARA/ARB) → Order Validity → EXECUTION GATE
```

| Condition | Result |
|-----------|--------|
| CONTINUOUS + OPEN + TRADEABLE + fresh | may PASS |
| FCA / HALTED / SUSPENDED / DELISTED | BLOCK |
| UNKNOWN / stale | BLOCK |
| PRE_OPEN / PRE_CLOSE / etc. | BLOCK |
| price > ARA / < ARB / off-tick / bad lot | BLOCK |

Broker is not primary validator. Gemini cannot override. LIVE/BROKER = FALSE.
