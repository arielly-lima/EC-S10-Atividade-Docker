"""Treinamento reutilizado pelo notebook e pelo container Docker."""

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

WINDOW = 7
FEATURES = [f"close_lag_{lag}" for lag in range(WINDOW, 0, -1)]
MODEL_PARAMS = {
    "n_estimators": 200,
    "max_depth": 10,
    "min_samples_leaf": 3,
    "random_state": 42,
    "n_jobs": -1,
}


def load_data(path):
    data = pd.read_csv(path, parse_dates=["date"])
    if not {"date", "close"}.issubset(data.columns):
        raise ValueError("O CSV deve conter date e close.")
    if data["date"].isna().any() or data["date"].duplicated().any():
        raise ValueError("Datas ausentes ou duplicadas.")
    data = data.sort_values("date").reset_index(drop=True)
    close = pd.to_numeric(data["close"], errors="raise").to_numpy(dtype=float)
    if not np.isfinite(close).all() or (close <= 0).any():
        raise ValueError("Fechamentos devem ser positivos e finitos.")
    if len(data) < WINDOW + 10:
        raise ValueError("Historico insuficiente para treino e teste.")
    return data


def make_samples(data):
    features, targets, dates = [], [], []
    skipped = 0
    for index in range(WINDOW, len(data)):
        block = data.iloc[index - WINDOW : index + 1]
        # Sete dias de entrada e o dia-alvo devem ser consecutivos.
        if not block["date"].diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
            skipped += 1
            continue
        features.append(block["close"].iloc[:-1].to_numpy(dtype=float))
        targets.append(float(block["close"].iloc[-1]))
        dates.append(block["date"].iloc[-1])
    if len(features) < 10:
        raise ValueError("Poucas sequencias consecutivas para avaliar o modelo.")
    return (
        pd.DataFrame(features, columns=FEATURES),
        np.asarray(targets),
        pd.DatetimeIndex(dates),
        skipped,
    )


def calculate_metrics(actual, prediction):
    return {
        "mae_usd": float(mean_absolute_error(actual, prediction)),
        "rmse_usd": float(np.sqrt(mean_squared_error(actual, prediction))),
    }


def train(data_path, output_dir):
    data_path, output_dir = Path(data_path), Path(output_dir)
    data = load_data(data_path)
    features, target, target_dates, skipped = make_samples(data)
    split = int(len(features) * 0.8)
    # Os 20% mais recentes ficam fora do ajuste usado na avaliacao.
    evaluation_model = RandomForestRegressor(**MODEL_PARAMS)
    evaluation_model.fit(features.iloc[:split], target[:split])
    predictions = evaluation_model.predict(features.iloc[split:])
    baseline = features.iloc[split:]["close_lag_1"].to_numpy()
    evaluation = {
        "split": "80% treino / 20% teste, em ordem cronologica",
        "train_samples": split,
        "test_samples": len(features) - split,
        "train_target_first_date": target_dates[0].date().isoformat(),
        "train_target_last_date": target_dates[split - 1].date().isoformat(),
        "test_target_first_date": target_dates[split].date().isoformat(),
        "test_target_last_date": target_dates[-1].date().isoformat(),
        "random_forest": calculate_metrics(target[split:], predictions),
        "baseline_last_close": calculate_metrics(target[split:], baseline),
    }

    # Apos a avaliacao, o artefato para inferencia aprende com todo o historico.
    # As metricas acima pertencem exclusivamente ao modelo de avaliacao.
    model = RandomForestRegressor(**MODEL_PARAMS)
    model.fit(features, target)
    last_week = data.tail(WINDOW)
    if not last_week["date"].diff().iloc[1:].eq(pd.Timedelta(days=1)).all():
        raise ValueError("Ultimos sete dias incompletos para demonstrar a previsao.")
    last_features = pd.DataFrame([last_week["close"].to_numpy()], columns=FEATURES)
    forecast = float(model.predict(last_features)[0])
    metadata = {
        "model_type": "RandomForestRegressor",
        "model_parameters": MODEL_PARAMS,
        "symbol": "BTC/USD",
        "currency": "USD",
        "timezone": "UTC",
        "horizon_days": 1,
        "window_days": WINDOW,
        "feature_names": FEATURES,
        "input_order": "Mais antigo para mais recente, sete dias consecutivos",
        "data_first_date": data["date"].iloc[0].date().isoformat(),
        "data_last_date": data["date"].iloc[-1].date().isoformat(),
        "data_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "data_rows": len(data),
        "usable_samples": len(features),
        "skipped_windows_due_to_gaps": skipped,
        "evaluation": evaluation,
        "exported_model_fit": "Todo o historico disponivel, depois da avaliacao",
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "joblib_version": joblib.__version__,
        "example": {
            "last_date": last_week["date"].iloc[-1].date().isoformat(),
            "closes": last_week["close"].tolist(),
            "prediction_date": (last_week["date"].iloc[-1] + pd.Timedelta(days=1)).date().isoformat(),
            "predicted_close_usd": forecast,
        },
        "limitations": [
            "Predicao experimental para demonstracao da integracao.",
            "Usa somente sete fechamentos; nao considera noticias ou fatores externos.",
            "Random Forest nao extrapola bem para precos fora da faixa observada.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / "model.joblib"
    joblib.dump({"model": model, "metadata": metadata}, artifact, compress=3)
    metadata["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    pd.DataFrame({
        "date": target_dates[split:].strftime("%Y-%m-%d"),
        "actual_close": target[split:],
        "predicted_close": predictions,
        "baseline_close": baseline,
    }).to_csv(output_dir / "test_predictions.csv", index=False)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/processed/btcusd_daily.csv")
    parser.add_argument("--output", default="models")
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.output), indent=2, ensure_ascii=False))
