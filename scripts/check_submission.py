"""Check saved local submission evidence using only the Python standard library.

Run from a Git checkout: python3 scripts/check_submission.py
Exit 0 means the LOCAL checks passed. Owner handoff and external review can still
be pending. This does not rerun tests, contact services, grade the project, inspect
secret contents, or certify scientific correctness or final compliance.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.0"
HADITH, PYTEST, CASES = 72, 137, 25   # release 0.6.0 corpus and evidence sizes
STATUSES = {"local_verified", "owner_handoff", "external_review_pending"}
WEIGHTS = {"technical_ai": 25, "scientific_safety": 15, "innovation": 15,
           "user_experience": 10, "benefit": 20, "operations": 10, "presentation": 5}
VALIDATION = "docs/evidence/backend-validation-v0.6.0-2026-10-04.json"
SAFETY = "docs/evidence/local-safety-v0.6.0-2026-10-04.json"


def local_file(name: str) -> Path:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError("Evidence path must stay inside the project")
    resolved = (ROOT / name).resolve()
    if not resolved.is_relative_to(ROOT) or not resolved.is_file():
        raise ValueError("Required local evidence file is absent or outside the project")
    return resolved


def read_json(name: str):
    return json.loads(local_file(name).read_text("utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence_paths(node) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence":
                if not isinstance(value, list) or not all(isinstance(p, str) for p in value):
                    raise ValueError("Evidence references must be lists of relative paths")
                found.update(value)
            else:
                found.update(evidence_paths(value))
    elif isinstance(node, list):
        for value in node:
            found.update(evidence_paths(value))
    return found


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def manifest_structure(manifest: dict) -> dict:
    require(manifest["schema_version"] == 1, "Unsupported manifest schema")
    require(manifest["project"]["release"] == VERSION, "Manifest release mismatch")
    require(manifest["scope"]["official_judging_score"] is False, "Manifest must not claim an official score")
    require(manifest["scope"]["guarantees_full_compliance"] is False, "Manifest must not guarantee final compliance")
    rows = manifest["requirements"]
    require(bool(rows) and len({r["id"] for r in rows}) == len(rows), "Requirement IDs must be unique")
    require(all(r["status"] in STATUSES and r["evidence"] for r in rows), "Invalid requirement status or absent evidence references")
    criteria = manifest["judging_criteria"]["criteria"]
    require(len(criteria) == 7 and {c["id"]: c["weight"] for c in criteria} == WEIGHTS, "Official criterion weight mapping changed")
    require(manifest["judging_criteria"]["weights_are_not_scores"] is True, "Criterion weights must not be presented as attained scores")
    require(manifest["project"]["demo_url"] == "https://tathabbut.vercel.app", "Demo URL mismatch")
    require(manifest["project"]["repository_url"] == "https://github.com/arifcoTeame/tathabbut", "Repository URL mismatch")
    return {"requirements": len(rows), "criterion_weights_total": sum(WEIGHTS.values()),
            "urls_checked": "Expected URL strings only; no network request"}


def references(manifest: dict) -> dict:
    paths = evidence_paths(manifest) | {v["path"] for v in manifest["data"].values()}
    missing = [name for name in sorted(paths) if not (ROOT / name).is_file()]
    require(not missing, "Required evidence is missing: " + ", ".join(missing))
    for name in paths:
        require(local_file(name).stat().st_size > 0, "An evidence file is empty")
    return {"existing_nonempty_references": len(paths), "meaning": "File existence, not approval of its substantive claims"}


def versions(manifest: dict) -> dict:
    tree = ast.parse(local_file("backend/app/core/pipeline.py").read_text("utf-8"))
    values = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(t, ast.Name) and t.id == "ENGINE_VERSION" for t in node.targets)
              and isinstance(node.value, ast.Constant)]
    require(values == [VERSION], "Backend engine version mismatch")
    package = read_json("frontend/package.json")
    lock = read_json("frontend/package-lock.json")
    require(package["version"] == lock["version"] == lock["packages"][""]["version"] == VERSION,
            "Frontend package and lockfile versions differ")
    require(read_json(VALIDATION)["engine_version"] == VERSION, "Saved validation version mismatch")
    return {"engine": VERSION, "frontend_package": VERSION, "lockfile": VERSION}


def data_counts(manifest: dict) -> dict:
    quran = read_json(manifest["data"]["quran"]["path"])["records"]
    hadith = read_json(manifest["data"]["hadith"]["path"])["records"]
    require(len(quran) == manifest["data"]["quran"]["records"] == 6236, "Quran count mismatch")
    require(len(hadith) == manifest["data"]["hadith"]["records"] == HADITH, "Hadith count mismatch")
    require(len({(r["surah"], r["ayah"]) for r in quran}) == 6236, "Duplicate Quran reference")
    require({r["surah"] for r in quran} == set(range(1, 115)), "Quran chapter identifiers differ")
    require(len({r["id"] for r in hadith}) == HADITH, "Duplicate hadith identifier")
    require(all(isinstance(r["text"], str) and r["text"].strip() for r in quran + hadith), "Empty source text")
    return {"quran": len(quran), "hadith": len(hadith), "meaning": "Structural count and identifier check; not independent source authentication"}


def saved_safety_results(manifest: dict) -> dict:
    safety, validation = read_json(SAFETY), read_json(VALIDATION)
    expected = manifest["local_checks"]["saved_test_expectations"]
    require(expected == {"pytest_passed": PYTEST, "release_distinct_inputs": CASES,
                        "release_repetitions": 3, "release_total": CASES * 3}, "Expected release evidence changed")
    rows = safety["cases"]
    require(safety["repeat"] == 3 and safety["passed"] == safety["total"] == len(rows) == CASES * 3,
            f"Saved release totals are not {CASES * 3} of {CASES * 3}")
    ids = {r["id"] for r in rows}
    require(len(ids) == CASES and len({(r["id"], r["run"]) for r in rows}) == CASES * 3, "Release cases are missing or duplicated")
    for case_id in ids:
        group = [r for r in rows if r["id"] == case_id]
        require({r["run"] for r in group} == {1, 2, 3}, "Each case requires three runs")
        require(len({r["input"] for r in group}) == 1, "A repeated input changed")
        require(len({tuple(r["expected"]) for r in group}) == 1, "A repeated expectation changed")
    for row in rows:
        response = row["response"]
        actual = [c["verdict"]["code"] for c in response["claims"]]
        require(row["passed"] is True and row["expected"] == row["actual"] == actual, "Saved verdict evidence is inconsistent")
        require(row["engine_version"] == response["engine_version"] == VERSION, "A saved result uses another engine version")
        require(response["index"]["quran"] == 6236 and response["index"]["hadith"] == HADITH, "Saved response corpus count differs")
    pytest = validation["pytest"]
    require(pytest["observed_exit_code"] == 0 and pytest["passed"] == PYTEST and pytest["failed"] == 0,
            "Saved pytest result is not successful")
    summary = validation["release_cases"]
    require(summary["distinct_inputs"] == CASES and summary["repetitions"] == 3
            and summary["passed"] == summary["total"] == CASES * 3, "Validation summary differs from release evidence")
    return {"distinct_cases": CASES, "repetitions": 3, "saved_passed": CASES * 3, "saved_total": CASES * 3,
            "saved_pytest_passed": PYTEST, "tests_rerun_by_this_checker": False}


def evidence_code_hashes(manifest: dict) -> dict:
    hashes = read_json(VALIDATION)["sha256"]
    require(bool(hashes), "No tested-code hashes recorded")
    for name, expected in hashes.items():
        require(sha256(local_file(name)) == expected, "A tested code or data file changed: " + name)
    return {"matching_tested_code_and_data_hashes": len(hashes)}


def retrieval_repeatability(manifest: dict) -> dict:
    primary = read_json("docs/evidence/retrieval-evaluation-2026-10-03.json")
    repeat = read_json("docs/evidence/retrieval-evaluation-repeat-2026-10-03.json")
    record = read_json("docs/evidence/retrieval-reproducibility-2026-10-03.json")
    require(primary["cases"] == repeat["cases"] and primary["groups"] == repeat["groups"], "Retrieval reruns differ")
    require(len(primary["cases"]) == 814 and all(record["checks"].values()), "Retrieval repeatability record is incomplete")
    for run in record["runs"]:
        require(sha256(local_file(run["file"])) == run["sha256"], "Retrieval evidence changed after repetition check")
    for name, expected in primary["code_sha256"].items():
        require(sha256(local_file(name)) == expected, "Retrieval code changed after measurement: " + name)
    require(sha256(local_file(primary["fixture"])) == primary["fixture_sha256"], "Frozen retrieval fixture changed")
    return {"queries_per_run": 814, "identical_rankings": True, "scope": "Synthetic reference retrieval only"}


def sensitive_filename(name: str) -> bool:
    parts = PurePosixPath(name).parts
    for part in parts:
        lower = part.lower()
        if lower == ".env.example":
            continue
        if lower == ".env" or lower.startswith(".env.") or lower.endswith(".env"):
            return True
        if lower in {".aws", ".ssh", ".npmrc", ".netrc", ".pypirc", "id_rsa", "id_ed25519", "id_ecdsa"}:
            return True
        if Path(lower).suffix in {".pem", ".key", ".p12", ".pfx", ".keystore"}:
            return True
        if re.search(r"(^|[._-])(secrets?|credentials?)([._-]|$)", lower):
            return True
    return False


def public_git_inventory(manifest: dict) -> dict:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                         check=True, capture_output=True, text=True).stdout.strip()
    require(Path(top).resolve() == ROOT, "Run this check inside the project's own Git checkout")
    raw = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                         cwd=ROOT, check=True, capture_output=True).stdout
    names = set(n.decode("utf-8") for n in raw.split(b"\0") if n)
    require(bool(names), "Public Git candidate list is empty")
    risk_count = sum(sensitive_filename(name) for name in names)
    require(risk_count == 0, f"Sensitive-looking filenames in public Git list: {risk_count}; inspect names locally before publishing")
    require(evidence_paths(manifest) <= names, "Some referenced evidence is absent from the public Git candidate list")
    return {"candidate_files": len(names), "risky_filename_count": risk_count,
            "file_contents_scanned": False, "secret_file_contents_read": False,
            "limitation": "Names only; this cannot detect a credential embedded in an ordinary source file"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/submission-check-v0.6.0.json")
    args = parser.parse_args()
    checks = []
    try:
        manifest = read_json("submission.json")
    except (OSError, ValueError) as exc:
        print(json.dumps({"local_checks_passed": False, "overall_ready": False,
                          "error": "Cannot read a valid submission manifest", "error_type": type(exc).__name__}))
        return 1
    for check in (manifest_structure, references, versions, data_counts, saved_safety_results,
                  evidence_code_hashes, retrieval_repeatability, public_git_inventory):
        try:
            details = check(manifest)
            checks.append({"id": check.__name__, "passed": True, "details": details})
        except (OSError, ValueError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as exc:
            # No file contents or subprocess output are included in a failure.
            message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
            checks.append({"id": check.__name__, "passed": False, "error": message})
    local_pass = all(check["passed"] for check in checks)
    requirements = manifest.get("requirements", [])
    pending = [{"id": r.get("id"), "label_ar": r.get("label_ar"), "status": r.get("status")}
               for r in requirements if r.get("status") != "local_verified"]
    report = {"checked_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(),
              "release": VERSION, "manifest_sha256": sha256(local_file("submission.json")),
              "scope": "Local consistency gate for saved evidence; no official score or final compliance certification",
              "network_used": False, "local_checks_passed": local_pass,
              "local_check_count": len(checks), "local_checks_passed_count": sum(c["passed"] for c in checks),
              "overall_ready": local_pass and not pending,
              "status_counts": dict(Counter(r.get("status", "invalid") for r in requirements)),
              "pending_requirements": pending, "checks": checks,
              "exit_policy": "Exit 0 for passed local checks even when owner handoff or external review is pending"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"local_checks_passed": local_pass, "local_passed": report["local_checks_passed_count"],
                      "local_total": len(checks), "overall_ready": report["overall_ready"],
                      "status_counts": report["status_counts"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if local_pass else 1


if __name__ == "__main__":
    sys.exit(main())
