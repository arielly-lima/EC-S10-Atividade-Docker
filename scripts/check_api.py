"""Verifica a integracao HTTP e a rejeicao de entradas invalidas."""

import argparse
import copy
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    try:
        with urlopen(Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=15) as response:
            content = response.read()
            return response.status, json.loads(content) if "json" in response.headers.get("Content-Type", "") else content.decode()
    except HTTPError as error:
        return error.code, json.loads(error.read())


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="evidence/api-validation.json")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    payload = json.loads((root / "examples/prediction_request.json").read_text(encoding="utf-8"))
    expected = json.loads((root / "models/metadata.json").read_text(encoding="utf-8"))["example"]
    results = []

    status, health = request(base + "/health")
    assert status == 200 and health["status"] == "ok" and health["model_loaded"] is True
    results.append({"case": "health", "status": status})
    status, prediction = request(base + "/predict", payload)
    assert status == 200
    assert prediction["prediction_date"] == expected["prediction_date"]
    assert abs(prediction["predicted_close"] - expected["predicted_close_usd"]) < 1e-6
    assert prediction["symbol"] == "BTC/USD" and prediction["currency"] == "USD"
    results.append({"case": "prediction_matches_exported_artifact", "status": status, "response": prediction})
    status, _ = request(base + "/docs")
    assert status == 200
    results.append({"case": "interactive_docs", "status": status})

    invalid = {"only_six_days": {"history": payload["history"][:-1]}}
    invalid["missing_day"] = copy.deepcopy(payload)
    invalid["missing_day"]["history"][3]["date"] = "2026-10-02"
    invalid["negative_price"] = copy.deepcopy(payload)
    invalid["negative_price"]["history"][0]["close"] = -1
    invalid["non_finite_price"] = copy.deepcopy(payload)
    invalid["non_finite_price"]["history"][0]["close"] = "Infinity"
    invalid["reverse_date_order"] = {"history": list(reversed(payload["history"]))}
    for case, bad_payload in invalid.items():
        status, _ = request(base + "/predict", bad_payload)
        assert status == 422, (case, status)
        results.append({"case": case, "status": status})

    evidence = {"base_url": base, "checks_passed": len(results), "results": results}
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
