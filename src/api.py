"""API Python que carrega o artefato e estima o proximo fechamento."""

import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import joblib
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, model_validator


@asynccontextmanager
async def lifespan(app):
    model_path = Path(os.getenv("MODEL_PATH", "models/model.joblib"))
    bundle = joblib.load(model_path)
    if bundle["metadata"]["window_days"] != 7 or bundle["metadata"]["horizon_days"] != 1:
        raise RuntimeError("Artefato incompativel: esperado sete dias de entrada e horizonte de um dia.")
    app.state.bundle = bundle
    yield


app = FastAPI(
    title="Predição de Bitcoin",
    description="Estimativa experimental do fechamento do dia seguinte a partir de sete dias de histórico.",
    lifespan=lifespan,
)


class DailyClose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    close: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"history": [
            {"date": "2026-09-28", "close": 83461.65},
            {"date": "2026-09-29", "close": 83629.41},
            {"date": "2026-09-30", "close": 83562.58},
            {"date": "2026-10-01", "close": 84852.65},
            {"date": "2026-10-02", "close": 84500.84},
            {"date": "2026-10-03", "close": 84746.87},
            {"date": "2026-10-04", "close": 86510.16},
        ]}]},
    )
    history: Annotated[list[DailyClose], Field(min_length=7, max_length=7)]

    @model_validator(mode="after")
    def consecutive_days(self):
        for previous, current in zip(self.history, self.history[1:]):
            if current.date != previous.date + timedelta(days=1):
                raise ValueError("Informe sete dias consecutivos, do mais antigo para o mais recente.")
        return self


class PredictionResponse(BaseModel):
    symbol: str
    currency: str
    prediction_date: date
    predicted_close: float
    horizon_days: int


@app.get("/health", summary="Verificar se o serviço está pronto")
def health():
    metadata = app.state.bundle["metadata"]
    return {
        "status": "ok",
        "model_loaded": True,
        "model": metadata["model_type"],
        "symbol": metadata["symbol"],
        "data_last_date": metadata["data_last_date"],
    }


@app.post("/predict", response_model=PredictionResponse, summary="Estimar o fechamento do próximo dia")
def predict(request: PredictionRequest):
    bundle = app.state.bundle
    values = [[day.close for day in request.history]]
    features = pd.DataFrame(values, columns=bundle["metadata"]["feature_names"])
    predicted_close = float(bundle["model"].predict(features)[0])
    return PredictionResponse(
        symbol=bundle["metadata"]["symbol"],
        currency=bundle["metadata"]["currency"],
        prediction_date=request.history[-1].date + timedelta(days=1),
        predicted_close=predicted_close,
        horizon_days=1,
    )
