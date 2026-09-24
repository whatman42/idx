# IDX enrichment cache

Production path reads **only** this local cache (or `IDX_ENRICHMENT_CACHE`).

- Do **not** treat live `idx.co.id` HTTP as SSOT.
- Corporate actions, liquidity stats, and sector labels should be loaded offline with provenance.
- Empty cache \u2192 gates pass with `NO_DATA` (not fail-closed until feed is certified).

See `src/python/idx_enrichment/` for authority matrix and pipeline order.
