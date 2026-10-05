"""Cliente simples que solicita uma predicao ao backend por HTTP."""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def request_json(url, payload=None):
    encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=encoded, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--request", default="examples/prediction_request.json")
    parser.add_argument("--output", default="evidence/inference.json")
    args = parser.parse_args()
    payload = json.loads((root / args.request).read_text(encoding="utf-8"))
    result = {
        "health": request_json(args.base_url.rstrip("/") + "/health"),
        "request": payload,
        "prediction": request_json(args.base_url.rstrip("/") + "/predict", payload),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
