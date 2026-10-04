"""Small release smoke check. Measures named cases, not general accuracy."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime
import json
from pathlib import Path
import time
import sys
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

CASES = [
    ("quran_exact", "﴿إياك نعبد وإياك نستعين﴾", ["VERIFIED"]),
    ("quran_changed_particle", "﴿إياك نعبد فإياك نستعين﴾", ["ALTERED"]),
    ("quran_missing_particle", "﴿إياك نعبد إياك نستعين﴾", ["ALTERED"]),
    ("quran_merged_quote", "﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾", ["ALTERED"]),
    ("quran_changed_word", "﴿لا يكلف الله نفسا إلا طاقتها﴾", ["ALTERED"]),
    ("quran_king_fahd_spelling", "﴿ولا تقربوا الزنا إنه كان فاحشة وساء سبيلا﴾", ["VERIFIED"]),
    ("quran_basmala_prefix", "﴿بسم الله الرحمن الرحيم قل هو الله أحد﴾", ["VERIFIED"]),
    ("hadith_authentic", "قال رسول الله ﷺ: «الدين النصيحة»", ["VERIFIED"]),
    ("hadith_recorded_weak", "قال رسول الله ﷺ: «حب الوطن من الإيمان»", ["NOT_AUTHENTIC"]),
    ("hadith_negation_removed", "قال رسول الله ﷺ: «يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه»", ["NEEDS_REVIEW"]),
    ("hadith_wording_changed", "قال رسول الله ﷺ: «اطلبوا العلم ولو في الصين»", ["NEEDS_REVIEW"]),
    ("outside_corpus", "قال رسول الله ﷺ: «الصبر مفتاح الفرج»", ["NO_ORIGIN"]),
    ("hadith_popular_not_established", "قال رسول الله ﷺ: «النظافة من الإيمان»", ["NOT_AUTHENTIC"]),
    ("hadith_hasan_grade", "قال رسول الله ﷺ: «إن الله تعالى يحب إذا عمل أحدكم عملا أن يتقنه»", ["VERIFIED"]),
    ("hadith_scholars_disagree", "قال رسول الله ﷺ: «خير الناس أنفعهم للناس»", ["DISPUTED"]),
    ("hadith_baseless_recorded", "قال رسول الله ﷺ: «من عرف نفسه فقد عرف ربه»", ["NOT_AUTHENTIC"]),
    ("hadith_fragment_of_long_text", "قال رسول الله ﷺ: «الكلمة الطيبة صدقة»", ["VERIFIED"]),
    ("hadith_popular_variant_wording", "قال رسول الله ﷺ: «إنما بعثت لأتمم مكارم الأخلاق»", ["NEEDS_REVIEW"]),
    ("hadith_extra_words_not_in_record", "قال رسول الله ﷺ: «الحكمة ضالة المؤمن أنى وجدها فهو أحق بها»", ["NO_ORIGIN"]),
    ("personal_referral", "هل يجوز لي أن أجمع الصلاة في العمل؟", ["REFER"]),
    ("multiple_claims", "قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين». وقال تعالى: ﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾. هل يجوز لي أن أجمع الصلاة في العمل؟", ["NOT_AUTHENTIC", "ALTERED", "REFER"]),
    ("personal_with_quran_same_sentence", "هل يجوز لي ترك الصلاة لأن الله قال: ﴿إن الله غفور رحيم﴾؟", ["REFER", "VERIFIED"]),
    ("personal_with_hadith_same_sentence", "هل يجوز لي أن أفعل ذلك بناء على حديث رسول الله ﷺ: «الدين النصيحة»؟", ["REFER", "VERIFIED"]),
    ("personal_after_quote", "قال رسول الله ﷺ: «الدين النصيحة»، فهل يحق لي نشر أسرار زوجتي؟", ["REFER", "VERIFIED"]),
    ("personal_after_unquoted_citation", "قال تعالى قل هو الله أحد، فهل يلزمني شيء في حالتي؟", ["REFER", "VERIFIED"]),
    ("first_person_quran_is_not_user_question", "قال تعالى: ﴿إني نذرت للرحمن صوما﴾", ["VERIFIED"]),
    ("referral_preserved_at_display_limit", "قال تعالى: ﴿قل هو الله أحد﴾. " * 12 + "هل يجوز لي ترك الصلاة؟", ["REFER"] + ["VERIFIED"] * 11),
]


def request(url: str, text: str | None = None):
    payload = None if text is None else json.dumps({"text": text}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--frontend", action="store_true")
    ap.add_argument("--in-process", action="store_true", help="Exercise FastAPI locally without opening a port")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.repeat < 1 or args.repeat > 3:
        ap.error("--repeat must be between 1 and 3")
    if args.in_process and args.frontend:
        ap.error("--in-process tests FastAPI, not the frontend proxy")
    base = args.base_url.rstrip("/")
    verify = "/api/verify" if args.frontend else "/verify"
    stats = "/api/stats" if args.frontend else "/index/stats"
    with ExitStack() as stack:
        call = lambda path, text=None: request(base + path, text)
        if args.in_process:
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from fastapi.testclient import TestClient
            from app.main import app
            client = stack.enter_context(TestClient(app))
            def call(path, text=None):
                result = client.get(path) if text is None else client.post(path, json={"text": text})
                result.raise_for_status()
                return result.json()
        report = {"checked_at": datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(),
                  "base_url": "FastAPI TestClient (in process)" if args.in_process else base,
                  "scope": f"{len(CASES)} targeted regression cases; not a representative accuracy benchmark",
                  "repeat": args.repeat, "index": call(stats), "cases": []}
        for run in range(1, args.repeat + 1):
            for name, text, expected in CASES:
                started = time.perf_counter()
                result = call(verify, text)
                actual = [claim["verdict"]["code"] for claim in result["claims"]]
                report["cases"].append({"id": name, "run": run, "input": text, "expected": expected,
                    "actual": actual, "passed": actual == expected,
                    "engine_version": result["engine_version"],
                    "roundtrip_ms": round((time.perf_counter() - started) * 1000),
                    "response": result})
    report["passed"] = sum(c["passed"] for c in report["cases"])
    report["total"] = len(report["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"passed": report["passed"], "total": report["total"],
                      "failed": [c["id"] for c in report["cases"] if not c["passed"]],
                      "output": str(args.output)}, ensure_ascii=False))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
