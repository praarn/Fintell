# backend/app/services/anomaly/ — explanation

Per-user unsupervised anomaly detection over spending, with a
human-readable "why this was flagged" attached to every result — not just
a score. Full rationale is in the root
[`IMPLEMENTATION.md`](../../../../IMPLEMENTATION.md) §10.

## The flow

```
service.run_anomaly_detection(db, user_id)
  triggered by POST /anomalies/detect and best-effort after every upload
│
├─ load the user's transactions + their suppressed signatures —
│     the (merchant.lower(), category) pairs of every flag they've
│     ever dismissed
│
├─ features.build_feature_matrix(transactions)
│     only OUTFLOWS are scored (a big deposit isn't the signal; letting
│     salary credits into the distribution would swamp everything)
│     6 features, each oriented so higher = more unusual:
│       amount_ratio_in_category, amount_magnitude_log, category_rarity,
│       merchant_novelty (binary), day_of_week_rarity,
│       time_of_month_rarity
│
├─ detector.detect(matrix, suppressed_signatures=…)
│     < ANOMALY_MIN_TRANSACTIONS (30) outflows → ([], model_trained=False)
│         — "no opinion", not "nothing is wrong"
│     else IsolationForest(n_estimators=200, contamination=0.05,
│          random_state=42).fit_predict + decision_function
│     _explain(): robust z-score per feature vs this user's own training
│         column; z ≥ ANOMALY_EXPLAIN_Z_THRESHOLD (2.0) → named driver,
│         ranked by z, each rendered as a templated sentence
│         ("Amount $1,180 is 18.9x your typical groceries spend ($62)")
│     a row whose signature is suppressed survives only if a HARD driver
│         (an amount feature) still fires — "I know I shop there"
│         silences a novel-merchant flag, not a 20x charge
│     severity is a presentation bucket on score (high/medium/low)
│
└─ reconcile anomaly_flags:
      new anomalies              → insert
      still anomalous            → update severity/score/drivers
      dismissed                  → never touched or recreated
      no longer anomalous & not
      dismissed                  → deleted (the user's normal moved)
```

## Files

| File | Role |
| --- | --- |
| `features.py` | the 6-feature spending feature space + the merchant/category signature keys used for dismissal suppression |
| `detector.py` | fits one `IsolationForest` per user, scores, derives the ranked explainability drivers |
| `service.py` | orchestration — refit, reconcile `anomaly_flags`, serve the feed, handle dismissals |

## Notes

- **One model per user, fit fresh on every run.** There is no persisted
  model artifact — retraining on the user's current history is cheap
  enough (and safer than drift) at this scale.
- **The "higher = more unusual" convention on every feature** is what
  lets the explainer treat "features far above this user's normal" as
  "features that drove the flag," with no per-feature direction
  handling.
- If the forest flags a joint outlier where no single feature clears the
  z-score bar, one honest "unusual combination" driver is emitted rather
  than fabricating a specific cause.
- Dismissals feed back into the *next* refit as "known normal" for that
  merchant/category pair — the model actually learns from user feedback,
  it doesn't just hide the flag client-side.
- Tested against a synthetic history with two injected anomalies: the
  suite asserts recall = 1.0 on the injected set with a 0.4 precision
  floor (demanding perfect precision on unlabelled "normal" rows would be
  dishonest — some are legitimately borderline).
