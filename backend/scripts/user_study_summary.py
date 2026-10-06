"""Summarise the 6 October task study (data/evaluation/user-study-2026-10-06.json).

Decision accuracy and self-timed seconds per method, per task, plus ratings.
Prints JSON and writes docs/evidence/user-study-2026-10-06.json. No statistics are
claimed beyond the counts: three participants are too few for significance tests.
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
data = json.loads((ROOT / "data" / "evaluation" / "user-study-2026-10-06.json").read_text("utf-8"))
tasks = {int(k): v for k, v in data["tasks"].items()}
rows = []
for p in data["responses"]:
    for task, method, decision, reason, sec, conf in p["answers"]:
        rows.append({"participant": p["participant"], "task": task, "method": "tathabbut" if method == "تثبّت" else "usual",
                     "correct": decision == tasks[task]["correct"], "undecided": decision == "لا أعرف",
                     "seconds": sec, "confidence": conf})


def stats(rs):
    return {"answers": len(rs), "correct": sum(r["correct"] for r in rs), "undecided": sum(r["undecided"] for r in rs),
            "mean_seconds": round(statistics.mean(r["seconds"] for r in rs), 1),
            "median_seconds": statistics.median(r["seconds"] for r in rs),
            "mean_confidence": round(statistics.mean(r["confidence"] for r in rs), 2)}


out = {
    "source": "data/evaluation/user-study-2026-10-06.json",
    "by_method": {m: stats([r for r in rows if r["method"] == m]) for m in ("tathabbut", "usual")},
    "by_task": {t: {m: stats([r for r in rows if r["task"] == t and r["method"] == m]) for m in ("tathabbut", "usual")}
                for t in sorted(tasks)},
    "tasks_faster_with_tathabbut": None,
    "ratings_mean": {k: round(statistics.mean(p["ratings"][k] for p in data["responses"]), 2) for k in ("ease", "clarity", "intent")},
    "comments": [p["comment"] for p in data["responses"]],
    "limits": [
        "Three participants recruited by the team; self-timed with a phone stopwatch; replies relayed by the project owner.",
        "Within-subject with alternating task halves, but with three people tasks 1–3 were done twice with the usual method and once with Tathabbut (and the reverse for 4–6).",
        "All six texts are in the platform's sources; for a hadith outside the base Tathabbut only refers to dorar.net and saves less time.",
        "No significance test is claimed; the result is a measured indication, not proof of general benefit.",
    ],
}
out["tasks_faster_with_tathabbut"] = sum(
    v["tathabbut"]["mean_seconds"] < v["usual"]["mean_seconds"] for v in out["by_task"].values())
(ROOT / "docs" / "evidence" / "user-study-2026-10-06.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", "utf-8")
print(json.dumps({k: out[k] for k in ("by_method", "tasks_faster_with_tathabbut", "ratings_mean")}, ensure_ascii=False, indent=1))
