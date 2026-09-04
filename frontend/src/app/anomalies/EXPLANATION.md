# frontend/src/app/anomalies/ — explanation

The anomaly feed — frontend for `anomaly/service` (root
`IMPLEMENTATION.md` §10).

## Flow

- `refresh()` loads the flag feed and stats together; a "Re-run
  detection" button calls `runAnomalyDetection()` and surfaces a plain-
  language notice built from the response (`model_trained` false → "not
  enough spending history yet... (N so far)"; true → "Model refit on N
  transactions · X new, Y cleared").
- `handleDismiss` is optimistic: it removes the flag from local state
  immediately, calls the API, and — only on failure — puts it back
  (re-sorted by score). No optimistic-update rollback is needed on
  success since the flag really is gone server-side.
- Each flag card lists its `driving_features` as a bulleted list of the
  plain-language `explanation` strings, with an optional `(Nσ)` suffix
  when a numeric z-score is present (binary drivers like
  `merchant_novelty` have `z_score: null`).

## Notes

- Severity chip colors (`high`/`medium`/`low`) are a direct map to the
  backend's presentation-bucket severity — no client-side re-bucketing
  of the raw score.
- The page copy explains the mechanism in one sentence for a technical
  reader: "IsolationForest over your own spending" + "dismissing a flag
  tells the model that pattern is normal for you" — matching the actual
  dismissal-suppression feedback loop, not a simplification of it.
