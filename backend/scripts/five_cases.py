"""The five user-review cases in three written forms, against a running API.

Usage: python3 -m scripts.five_cases --base-url https://tathabbut.vercel.app --frontend --output out.json
Checks the verdict, that the attribution phrase is not part of the matched text,
and the source link of each card.
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

CASES = [
    # id, expected verdict, three forms: original with ﷺ / hamza + diacritics / plain
    ("watan", "NOT_AUTHENTIC", [
        "قال رسول الله ﷺ: «حب الوطن من الإيمان»",
        "قالَ رسولُ اللهِ ﷺ: «حُبُّ الوَطَنِ مِنَ الإيمانِ»",
        "قال رسول الله حب الوطن من الايمان",
    ], "حب الوطن من الإيمان"),
    ("taqa", "ALTERED", [
        "قال تعالى: ﴿لا يكلف الله نفسًا إلا طاقتها﴾",
        "قالَ تعالى: ﴿لَا يُكَلِّفُ اللَّهُ نَفْسًا إِلَّا طَاقَتَهَا﴾",
        "قال تعالى لا يكلف الله نفسا الا طاقتها",
    ], "لا يكلف الله نفسا"),
    ("anfa", "DISPUTED", [
        "قال رسول الله ﷺ: «خير الناس أنفعهم للناس»",
        "قالَ رسولُ اللهِ ﷺ: «خَيْرُ النَّاسِ أَنْفَعُهُمْ لِلنَّاسِ»",
        "قال رسول الله خير الناس انفعهم للناس",
    ], "خير الناس"),
    ("makarim", "NEEDS_REVIEW", [
        "قال رسول الله ﷺ: «إنما بعثت لأتمم مكارم الأخلاق»",
        "قالَ رسولُ اللهِ ﷺ: «إِنَّمَا بُعِثْتُ لِأُتَمِّمَ مَكَارِمَ الأَخْلَاقِ»",
        "قال رسول الله انما بعثت لاتمم مكارم الاخلاق",
    ], "بعثت"),
    ("sabr", "NO_ORIGIN", [
        "قال رسول الله ﷺ: «الصبر مفتاح الفرج»",
        "قالَ رسولُ اللهِ ﷺ: «الصَّبْرُ مِفْتَاحُ الفَرَجِ»",
        "قال رسول الله الصبر مفتاح الفرج",
    ], "الصبر مفتاح الفرج"),
]
LEADS = ("قال", "رسول", "تعالى", "ﷺ")


def post(url, text):
    req = urllib.request.Request(url, json.dumps({"text": text}).encode(), {"content-type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r), round(time.time() - t, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--frontend", action="store_true")
    ap.add_argument("--output", type=Path)
    a = ap.parse_args()
    url = a.base_url.rstrip("/") + ("/api/verify" if a.frontend else "/verify")
    rows, ok = [], 0
    for cid, expected, forms, _ in CASES:
        for form, text in zip(("original", "diacritics", "plain"), forms):
            body, secs = post(url, text)
            c = body["claims"][0]
            claim_text = c["text"]
            lead_free = not any(claim_text.strip().startswith(w) for w in LEADS) and "ﷺ" not in claim_text
            src = c.get("source") or {}
            passed = c["verdict"]["code"] == expected and lead_free and len(body["claims"]) == 1
            ok += passed
            rows.append({
                "case": cid, "form": form, "input": text, "matched_text": claim_text,
                "attribution_excluded": lead_free, "verdict": c["verdict"]["code"], "expected": expected,
                "source": src.get("ref", {}).get("surah_name") or src.get("id"), "source_url": src.get("url"),
                "grades": [g["grade"] + " — " + g["muhaddith"] for g in c.get("grades", [])],
                "diff": [d for d in c.get("diff", []) if d["op"] != "equal"],
                "engine_version": body.get("engine_version"), "seconds": secs, "passed": passed,
            })
            print(cid, form, c["verdict"]["code"], "lead-free" if lead_free else "LEAD!", "OK" if passed else "FAIL", secs)
    out = {"recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "endpoint": url, "passed": ok, "total": len(rows), "rows": rows}
    if a.output:
        a.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": ok, "total": len(rows)}))


if __name__ == "__main__":
    main()
