import logging

import joblib
import pandas as pd

from backend import config
from backend.stats_layer import STATS_PATH, StatsLayer

log = logging.getLogger("model")

USE_STATS = getattr(config, "USE_STATS_LAYER", True)


class AnomalyModel:
    """Layer 1: Isolation Forest (score).  Layer 2: statistics (z-score + Mahalanobis).

    Window anomalous maani jati hai agar KOI BHI layer flag kare ("any" rule).
    predict() ka return (score, is_anomaly) pehle jaisa hi hai, to main.py me badlav nahi.
    """

    def __init__(self, path=config.MODEL_PATH):
        self.pipeline = joblib.load(path)
        self.stats = None
        self.last_detail = None
        if USE_STATS:
            if STATS_PATH.exists():
                self.stats = StatsLayer.load(STATS_PATH)
                if self.stats.names != list(config.FEATURE_NAMES):
                    raise ValueError(
                        "stats.pkl alag features se bana hai. python -m ml.train dobara chalao."
                    )
                log.info("Stats layer loaded (Mahalanobis threshold %.2f)", self.stats.maha_threshold)
            else:
                log.warning("stats.pkl nahi mila -> sirf Isolation Forest chal raha hai (python -m ml.train)")

    def predict_detail(self, features: dict[str, float]) -> dict:
        X = pd.DataFrame([features], columns=config.FEATURE_NAMES)
        score = float(self.pipeline.decision_function(X)[0])
        if_flag = bool(self.pipeline.predict(X)[0] == -1)

        stats = self.stats.score(features) if self.stats else None
        stats_flag = bool(stats and stats["flag"])

        reasons = []
        if if_flag:
            reasons.append(f"IsolationForest score {score:.3f}")
        if stats:
            reasons += stats["reasons"]

        detail = {
            "score": score,
            "if_flag": if_flag,
            "stats_flag": stats_flag,
            "is_anomaly": if_flag or stats_flag,
            "maha": stats["maha"] if stats else None,
            "z": stats["z"] if stats else None,
            "reasons": reasons,
        }
        self.last_detail = detail
        if detail["is_anomaly"]:
            log.warning("ANOMALY window: %s", "; ".join(reasons))
        return detail

    def predict(self, features: dict[str, float]) -> tuple[float, bool]:
        """Returns (score, is_anomaly). Score jitna negative, utna anomalous (Isolation Forest)."""
        d = self.predict_detail(features)
        return d["score"], d["is_anomaly"]

    def predict_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """Poori CSV ek saath (evaluate.py ke liye). Same logic, vectorised."""
        X = df[config.FEATURE_NAMES]
        out = pd.DataFrame(index=df.index)
        out["score"] = self.pipeline.decision_function(X)
        out["if_flag"] = self.pipeline.predict(X) == -1
        if self.stats:
            Z, d, flag = self.stats.evaluate(X.to_numpy(float))
            out["maha"] = d
            out["stats_flag"] = flag
            out["top_feature"] = [self.stats.names[i] for i in abs(Z).argmax(axis=1)]
        else:
            out["maha"], out["stats_flag"], out["top_feature"] = float("nan"), False, ""
        out["is_anomaly"] = out["if_flag"] | out["stats_flag"]
        return out
