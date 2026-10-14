from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib

from . import config
from .db import get_conn, get_config_value, now_iso

FEATURE_NAMES = [
    "hist_avg_volume",
    "hist_avg_duration",
    "hist_avg_flow",
    "hist_avg_pauses",
    "hist_avg_temp",
    "hour",
    "weekday",
]


def _history_feature_rows() -> tuple[list[list[float]], list[float]]:
    """Builds leakage-reduced training rows using only prior sessions of each resident."""
    X: list[list[float]] = []
    y: list[float] = []
    with get_conn() as conn:
        residents = conn.execute("SELECT id FROM residents ORDER BY id").fetchall()
        for resident in residents:
            sessions = conn.execute(
                "SELECT * FROM sessions WHERE resident_id=? AND status='FINALIZADA' AND quality='VALIDA' AND experimental=1 "
                "ORDER BY started_at,id",
                (resident["id"],),
            ).fetchall()
            history: list[Any] = []
            for s in sessions:
                if len(history) >= 2:
                    started = datetime.fromisoformat(s["started_at"]) if s["started_at"] else datetime.now()
                    X.append([
                        sum(h["volume_total_l"] for h in history) / len(history),
                        sum(h["effective_duration_s"] for h in history) / len(history),
                        sum((h["avg_flow_lmin"] or 0) for h in history) / len(history),
                        sum(h["pause_count"] for h in history) / len(history),
                        sum((h["avg_temp_c"] or 24) for h in history) / len(history),
                        float(started.hour),
                        float(started.weekday()),
                    ])
                    y.append(float(s["volume_total_l"]))
                history.append(s)
    return X, y


def train_models() -> dict[str, Any]:
    try:
        from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import KFold, cross_val_predict
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "message": f"scikit-learn no disponible: {exc}"}

    X, y = _history_feature_rows()
    if len(y) < 12:
        return {"ok": False, "message": "No existen suficientes observaciones históricas válidas para evaluar modelos."}

    models = {
        "Regresión lineal": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=180, max_depth=6, random_state=2026),
        "Gradient Boosting": GradientBoostingRegressor(random_state=2026),
    }
    n_splits = min(5, max(3, len(y) // 8))
    cv = KFold(n_splits=n_splits, shuffle=True, random_state=2026)
    results: list[dict[str, Any]] = []

    with get_conn() as conn:
        conn.execute("UPDATE ai_models SET active=0")
        for algorithm, model in models.items():
            preds = cross_val_predict(model, X, y, cv=cv)
            mae = float(mean_absolute_error(y, preds))
            rmse = float(math.sqrt(mean_squared_error(y, preds)))
            r2 = float(r2_score(y, preds))
            model.fit(X, y)
            safe_name = algorithm.lower().replace(" ", "_").replace("ó", "o")
            version = f"{safe_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            model_filename = f"{version}.joblib"
            model_path = config.MODELS_DIR / model_filename
            joblib.dump({"model": model, "features": FEATURE_NAMES, "algorithm": algorithm}, model_path)
            conn.execute(
                "INSERT INTO ai_models(algorithm,version,mae,rmse,r2,sample_size,active,metadata_json,file_path) VALUES(?,?,?,?,?,?,0,?,?)",
                (algorithm, version, mae, rmse, r2, len(y), json.dumps({"cv_splits": n_splits, "features": FEATURE_NAMES}), model_filename),
            )
            model_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            results.append({"id": model_id, "algorithm": algorithm, "version": version, "mae": mae, "rmse": rmse, "r2": r2, "sample_size": len(y), "path": model_filename})

        best = min(results, key=lambda r: (r["mae"], r["rmse"]))
        conn.execute("UPDATE ai_models SET active=1 WHERE id=?", (best["id"],))

    return {"ok": True, "models": results, "selected": best}


def list_models() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM ai_models ORDER BY trained_at DESC,id DESC").fetchall()
    return [dict(r) for r in rows]


def active_model() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ai_models WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None


def resident_features(resident_id: int, when: datetime | None = None) -> tuple[list[float] | None, int]:
    when = when or datetime.now()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE resident_id=? AND status='FINALIZADA' AND quality='VALIDA' AND experimental=1 ORDER BY started_at,id",
            (resident_id,),
        ).fetchall()
    min_history = int(config.MIN_HISTORY_FOR_AI)
    if len(rows) < min_history:
        return None, len(rows)
    return [
        sum(r["volume_total_l"] for r in rows) / len(rows),
        sum(r["effective_duration_s"] for r in rows) / len(rows),
        sum((r["avg_flow_lmin"] or 0) for r in rows) / len(rows),
        sum(r["pause_count"] for r in rows) / len(rows),
        sum((r["avg_temp_c"] or 24) for r in rows) / len(rows),
        float(when.hour),
        float(when.weekday()),
    ], len(rows)


def predict_for_resident(resident_id: int, reduction_pct: float | None = None, session_id: int | None = None, freeze: bool = True) -> dict[str, Any]:
    reduction_pct = float(reduction_pct if reduction_pct is not None else get_config_value("ai_reduction_pct", config.AI_REDUCTION_PCT))
    features, history_count = resident_features(resident_id)
    if not features:
        return {"ok": False, "reason": "INSUFFICIENT_HISTORY", "history_count": history_count, "required": config.MIN_HISTORY_FOR_AI}

    model_row = active_model()
    if not model_row:
        trained = train_models()
        if not trained.get("ok"):
            return trained
        model_row = active_model()
    if not model_row or not model_row.get("file_path"):
        return {"ok": False, "reason": "MODEL_NOT_AVAILABLE"}
    model_path = Path(model_row["file_path"])
    if not model_path.is_absolute():
        model_path = config.MODELS_DIR / model_path
    if not model_path.exists():
        return {"ok": False, "reason": "MODEL_NOT_AVAILABLE"}

    package = joblib.load(model_path)
    predicted = float(package["model"].predict([features])[0])
    predicted = max(5.0, predicted)
    target = max(5.0, predicted * (1.0 - reduction_pct / 100.0))

    result = {
        "ok": True,
        "resident_id": resident_id,
        "model_id": model_row["id"],
        "model_version": model_row["version"],
        "algorithm": model_row["algorithm"],
        "predicted_l": round(predicted, 2),
        "target_l": round(target, 2),
        "reduction_pct": round(reduction_pct, 2),
        "history_count": history_count,
        "features": dict(zip(FEATURE_NAMES, [round(x, 3) for x in features])),
    }
    if freeze:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO ai_predictions(resident_id,session_id,model_id,predicted_l,target_l,reduction_pct,frozen,created_at) VALUES(?,?,?,?,?,?,1,?)",
                (resident_id, session_id, model_row["id"], predicted, target, reduction_pct, now_iso()),
            )
            conn.execute("UPDATE consumption_targets SET active=0 WHERE resident_id=?", (resident_id,))
            conn.execute(
                "INSERT INTO consumption_targets(resident_id,source,predicted_l,reduction_pct,target_l,model_version,active,created_at) VALUES(?,?,?,?,?,?,1,?)",
                (resident_id, "IA", predicted, reduction_pct, target, model_row["version"], now_iso()),
            )
            conn.execute("UPDATE residents SET default_goal_l=? WHERE id=?", (target, resident_id))
    return result


def ai_dashboard(resident_id: int | None = None) -> dict[str, Any]:
    with get_conn() as conn:
        if resident_id is None:
            row = conn.execute("SELECT id FROM residents WHERE code='R-003'").fetchone()
            resident_id = row["id"] if row else 1
        resident = conn.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
        sessions = conn.execute(
            "SELECT * FROM sessions WHERE resident_id=? AND status='FINALIZADA' AND quality='VALIDA' AND experimental=1 ORDER BY started_at",
            (resident_id,),
        ).fetchall()
        pred = conn.execute(
            "SELECT p.*,m.algorithm,m.version FROM ai_predictions p LEFT JOIN ai_models m ON m.id=p.model_id WHERE p.resident_id=? ORDER BY p.id DESC LIMIT 1",
            (resident_id,),
        ).fetchone()

    if sessions:
        vols = [float(s["volume_total_l"]) for s in sessions]
        trend = ((vols[-1] - vols[0]) / vols[0] * 100) if vols[0] else 0
        hours = [datetime.fromisoformat(s["started_at"]).hour for s in sessions if s["started_at"]]
        weekdays = [datetime.fromisoformat(s["started_at"]).weekday() for s in sessions if s["started_at"]]
        peak_hour = int(round(sum(hours) / len(hours))) if hours else 8
        day_names = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]
        top_day = max(set(weekdays), key=weekdays.count) if weekdays else 0
    else:
        trend, peak_hour, top_day = 0.0, 8, 0
        day_names = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"]

    return {
        "resident": dict(resident) if resident else None,
        "prediction": dict(pred) if pred else None,
        "patterns": {
            "trend_pct": round(trend, 1),
            "peak_window": f"{peak_hour:02d}:00 - {(peak_hour+1):02d}:30",
            "top_day": day_names[top_day],
            "message": "Mayor ahorro en modo inteligente" if sessions else "Sin datos suficientes",
        },
        "models": list_models()[:6],
    }
