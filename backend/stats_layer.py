"""Statistics layer: har feature ka z-score + Mahalanobis distance (sirf healthy data se fit).

Kaam:
  * z-score   : "kaunsa feature normal se kitna door hai" (explanation ke liye)
  * Mahalanobis: saare features ko saath dekhta hai (correlation ke saath). Ek feature ka value
                 normal range me ho par combination ajeeb ho (jaise current kam par vibration zyada),
                 to bhi pakad leta hai.

Thresholds config.py me optionally override ho sakte hain (na ho to neeche ke defaults):
  Z_LIMIT, MAHA_MARGIN, STD_REL_FLOOR, STATS_PATH
"""
from pathlib import Path

import joblib
import numpy as np
from sklearn.covariance import LedoitWolf

from backend import config

Z_LIMIT = getattr(config, "Z_LIMIT", 6.0)               # |z| isse zyada -> flag
MAHA_MARGIN = getattr(config, "MAHA_MARGIN", 1.5)       # threshold = training 99.9 percentile * margin
STD_REL_FLOOR = getattr(config, "STD_REL_FLOOR", 0.01)  # std kam se kam mean ka 1% (near-constant sensor pe z na phate)
STATS_PATH = Path(getattr(config, "STATS_PATH", Path(config.MODEL_PATH).with_name("stats.pkl")))


class StatsLayer:
    def __init__(self, names, mean, std, floored, location, precision, maha_threshold, z_limit):
        self.names = list(names)
        self.mean = np.asarray(mean, float)
        self.std = np.asarray(std, float)
        self.floored = np.asarray(floored, bool)
        self.location = np.asarray(location, float)
        self.precision = np.asarray(precision, float)
        self.maha_threshold = float(maha_threshold)
        self.z_limit = float(z_limit)

    # ---------- training ----------
    @classmethod
    def fit(cls, df, names):
        X = df[list(names)].to_numpy(float)
        mean = X.mean(axis=0)
        raw_std = X.std(axis=0, ddof=1) if len(X) > 1 else np.zeros(X.shape[1])
        floor = np.maximum(STD_REL_FLOOR * np.abs(mean), 1e-6)
        std = np.maximum(raw_std, floor)
        Z = (X - mean) / std

        # Ledoit-Wolf shrinkage: i_mean/i_max jaise correlated features pe covariance singular na ho
        lw = LedoitWolf().fit(Z)
        layer = cls(names, mean, std, raw_std < floor, lw.location_, lw.precision_, 0.0, Z_LIMIT)
        d = layer.maha(Z)
        layer.maha_threshold = float(np.quantile(d, 0.999) * MAHA_MARGIN)
        return layer

    # ---------- scoring ----------
    def z_matrix(self, X):
        return (np.asarray(X, float) - self.mean) / self.std

    def maha(self, Z):
        D = Z - self.location
        return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", D, self.precision, D), 0.0))

    def evaluate(self, X):
        """X: (n, d) array. Returns (Z, maha, flag)."""
        Z = self.z_matrix(X)
        d = self.maha(Z)
        flag = (d > self.maha_threshold) | (np.abs(Z) > self.z_limit).any(axis=1)
        return Z, d, flag

    def score(self, features: dict) -> dict:
        x = np.array([[features[n] for n in self.names]], float)
        Z, d, flag = self.evaluate(x)
        z = Z[0]
        order = np.argsort(-np.abs(z))
        reasons = []
        if d[0] > self.maha_threshold:
            reasons.append(f"Mahalanobis {d[0]:.1f} > {self.maha_threshold:.1f}")
        for j in order:
            if abs(z[j]) > self.z_limit:
                reasons.append(f"{self.names[j]} z={z[j]:+.1f}")
        return {
            "flag": bool(flag[0]),
            "maha": float(d[0]),
            "maha_threshold": self.maha_threshold,
            "z": {n: float(v) for n, v in zip(self.names, z)},
            "top": [(self.names[j], float(z[j])) for j in order[:3]],
            "reasons": reasons,
        }

    # ---------- save / load ----------
    def save(self, path=STATS_PATH):
        joblib.dump(self.__dict__, path)

    @classmethod
    def load(cls, path=STATS_PATH):
        return cls(**joblib.load(path))
