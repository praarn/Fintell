"""Per-user IsolationForest over the hand-built spending feature space.

What's genuinely ML here: `IsolationForest` finds transactions that are
easy to isolate in the joint feature space — the joint-outlier detector.
What's a heuristic (and labelled as such): the severity buckets, and the
"which feature drove this" explanation, which is a robust z-score of each
feature against the same training rows, not an SHAP-style attribution.
"""

import uuid
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import IsolationForest

from app.core.config import get_settings
from app.services.anomaly.features import (
    BINARY_FEATURES,
    FEATURE_NAMES,
    TransactionFeatures,
    build_feature_rows,
    explanation_for,
)

settings = get_settings()

_RANDOM_STATE = 42
_MAD_TO_STD = 1.4826  # makes MAD a consistent estimator of stddev for normal data
_BINARY_RARE_FRACTION = 0.35  # a 0/1 feature is only a "driver" if <35% of rows have it set

# decision_function is centred so that ~`contamination` of training rows fall
# below 0. These cutoffs on top of that are a presentation choice.
_SEVERITY_HIGH_BELOW = -0.12
_SEVERITY_MEDIUM_BELOW = -0.04


@dataclass
class AnomalyResult:
    transaction_id: uuid.UUID
    score: float
    severity: str
    drivers: list[dict] = field(default_factory=list)


def _severity(score: float) -> str:
    if score <= _SEVERITY_HIGH_BELOW:
        return "high"
    if score <= _SEVERITY_MEDIUM_BELOW:
        return "medium"
    return "low"


def _robust_z(column: np.ndarray, value: float) -> float:
    median = float(np.median(column))
    mad = float(np.median(np.abs(column - median)))
    if mad < 1e-9:
        std = float(np.std(column))
        if std < 1e-9:
            return 0.0
        return (value - median) / std
    return (value - median) / (_MAD_TO_STD * mad)


def _explain(
    matrix: np.ndarray, row: TransactionFeatures, z_threshold: float
) -> list[dict]:
    """Rank the features on which this row sits well above the user's
    normal. Every feature is oriented higher = more unusual, so we only
    care about positive z."""
    drivers: list[dict] = []
    for j, name in enumerate(FEATURE_NAMES):
        value = row.values[name]
        if name in BINARY_FEATURES:
            if value >= 1.0 and float(np.mean(matrix[:, j])) <= _BINARY_RARE_FRACTION:
                drivers.append(
                    {
                        "feature": name,
                        "explanation": explanation_for(name, row),
                        "z_score": None,
                        "value": round(value, 3),
                    }
                )
            continue

        z = _robust_z(matrix[:, j], value)
        if z >= z_threshold:
            drivers.append(
                {
                    "feature": name,
                    "explanation": explanation_for(name, row),
                    "z_score": round(z, 2),
                    "value": round(value, 3),
                }
            )

    drivers.sort(key=lambda d: (d["z_score"] is not None, d["z_score"] or 0.0), reverse=True)

    if not drivers:
        # IsolationForest flagged a joint outlier where no single feature
        # cleared the bar — still say something honest rather than nothing.
        drivers.append(
            {
                "feature": "combination",
                "explanation": (
                    "Unusual combination of amount, timing, and merchant relative to "
                    "your history"
                ),
                "z_score": None,
                "value": None,
            }
        )
    return drivers


def detect(
    transactions: list,
    *,
    suppressed_signatures: set[tuple[str, str]] | None = None,
) -> tuple[list[AnomalyResult], bool]:
    """Fit a fresh per-user IsolationForest and return the flagged rows.

    Returns `(results, model_trained)`. `model_trained` is False when the
    user doesn't have enough outflow history yet — the caller should treat
    that as "no opinion", not "nothing is wrong".

    `suppressed_signatures` is the dismissal feedback loop: a set of
    `(merchant, category)` pairs the user has already told us are normal.
    A row matching one is only kept if something *hard* (an amount feature)
    still drives it — "I know I shop there" shouldn't excuse a 20x charge.
    """
    suppressed = suppressed_signatures or set()
    rows = build_feature_rows(transactions)
    if len(rows) < settings.anomaly_min_transactions:
        return [], False

    matrix = np.array([r.row() for r in rows], dtype=float)

    model = IsolationForest(
        n_estimators=200,
        contamination=settings.anomaly_contamination,
        random_state=_RANDOM_STATE,
    )
    predictions = model.fit_predict(matrix)
    scores = model.decision_function(matrix)

    results: list[AnomalyResult] = []
    for row, prediction, score in zip(rows, predictions, scores, strict=True):
        if prediction != -1:
            continue

        drivers = _explain(matrix, row, settings.anomaly_explain_z_threshold)

        signature = (row.merchant.lower(), row.category)
        if signature in suppressed:
            hard_driver = any(
                d["feature"] in ("amount_ratio_in_category", "amount_magnitude_log")
                for d in drivers
            )
            if not hard_driver:
                continue

        results.append(
            AnomalyResult(
                transaction_id=row.transaction_id,
                score=float(score),
                severity=_severity(float(score)),
                drivers=drivers,
            )
        )

    return results, True
