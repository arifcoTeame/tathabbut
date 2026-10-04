"""Capture selected searches from Dorar's documented API for manual review.

This does not update the seed or mark any hadith verified. Access to the API
does not grant permission to redistribute a local corpus. Confirm the permitted
use before fetching. A denial or rate limit stops the batch; there is no retry
or alternate endpoint. Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "https://dorar.net/dorar_api.json"
API_DOCUMENTATION = "https://dorar.net/article/389"
MAX_RESPONSE_BYTES = 5_000_000


def api_url(query: str) -> str:
    return ENDPOINT + "?" + urlencode({"skey": query})


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)


def validate_snapshot(snapshot: dict) -> dict:
    query = snapshot["query"]
    if snapshot.get("request_url") != api_url(query):
        raise ValueError("Snapshot URL does not match the official API and query")
    body = snapshot["response_text"].encode("utf-8")
    if hashlib.sha256(body).hexdigest() != snapshot.get("response_sha256"):
        raise ValueError("Snapshot response hash mismatch")
    parsed = json.loads(body)
    if not isinstance(parsed, dict) or "ahadith" not in parsed:
        raise ValueError("The response is not a Dorar hadith API response")
    captured = datetime.fromisoformat(snapshot["retrieved_at"].replace("Z", "+00:00"))
    if captured.tzinfo is None:
        raise ValueError("Snapshot retrieval time must include its timezone")
    return parsed


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch(query: str) -> dict:
    url = api_url(query)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "TathabbutSourceReview/0.1"})
    with build_opener(NoRedirect).open(request, timeout=30) as response:
        if urlparse(response.url).hostname != "dorar.net":
            raise ValueError("Unexpected response host")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("API response exceeds the capture limit")
    snapshot = {
        "schema_version": 1,
        "query": query,
        "request_url": url,
        "api_documentation": API_DOCUMENTATION,
        "retrieved_at": timestamp(),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "response_text": body.decode("utf-8"),
    }
    validate_snapshot(snapshot)
    return snapshot


def run(candidates: list[dict], output: Path, limit: int, delay: float) -> dict:
    ids = [candidate["id"] for candidate in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("Candidate IDs must be unique")
    if not 1 <= limit <= 95:
        raise ValueError("Search limit must be between 1 and 95")
    for candidate in candidates:
        key, query = candidate["id"], candidate["query"]
        if not re.fullmatch(r"[a-z0-9-]+", key) or not isinstance(query, str) or not query.strip():
            raise ValueError("Invalid candidate ID or empty query")
    status_path = output / "status.json"
    status = json.loads(status_path.read_text("utf-8")) if status_path.exists() else {"schema_version": 1, "queries": {}}
    requested = 0
    for candidate in candidates:
        key, query = candidate["id"], candidate["query"]
        path = output / f"{key}.json"
        if path.exists():
            snapshot = json.loads(path.read_text("utf-8"))
            validate_snapshot(snapshot)
            if snapshot["query"] != query:
                raise ValueError(f"Cached query changed for {key}; review it before continuing")
            continue
        if requested >= limit:
            break
        if requested:
            time.sleep(max(1.0, delay))
        requested += 1
        attempt = {"query": query, "request_url": api_url(query), "attempted_at": timestamp()}
        try:
            snapshot = fetch(query)
            write_json(path, snapshot)
            attempt.update(state="captured_unreviewed", snapshot=path.name)
        except HTTPError as exc:
            state = "access_denied" if exc.code in (401, 403) else "rate_limited" if exc.code == 429 else "http_error"
            attempt.update(state=state, http_status=exc.code)
        except (URLError, TimeoutError, ValueError, UnicodeError) as exc:
            attempt.update(state="error", error=str(exc))
        status["queries"][key] = attempt
        status["updated_at"] = timestamp()
        write_json(status_path, status)
        print(f"{key}: {attempt['state']}", flush=True)
        if attempt["state"] != "captured_unreviewed":
            break
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=Path(__file__).with_name("hadith_candidates.json"))
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "review" / "hadith_dorar")
    parser.add_argument("--limit", type=int, default=5, help="Maximum new searches; default 5")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between searches; at least one")
    parser.add_argument("--confirm-permitted-use", action="store_true", help="Confirm permission for this use; this flag does not grant permission")
    args = parser.parse_args()
    if not args.confirm_permitted_use:
        parser.error("Confirm the permitted use of source data before fetching (--confirm-permitted-use)")
    if args.limit < 1 or args.limit > 95:
        parser.error("--limit must be between 1 and 95")
    try:
        data = json.loads(args.candidates.read_text("utf-8"))
        status = run(data["candidates"], args.output, args.limit, args.delay)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1
    failures = [r for r in status["queries"].values() if r["state"] != "captured_unreviewed"]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
