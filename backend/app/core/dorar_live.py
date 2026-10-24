"""Live lookup in Dorar's hadith encyclopedia (dorar.net/dorar_api.json).

Used only when a hadith is not in the platform's own base. Nothing is stored
beyond a short in-memory cache: each lookup asks Dorar, reads the rulings it
returns, and passes them through the same word alignment as local records.

Rules that keep the result honest:
* A ruling is shown only for a Dorar record whose wording contains the quoted
  text word for word; a close but different wording is shown as "similar".
* Rulings are copied verbatim with their muhaddith and source. The platform
  never writes a grade of its own: it only says whether every ruling it could
  read accepts the hadith, rejects it, or the rulings differ.
* Dorar's search returns at most 15 records per request, so the result covers
  those records only, and the card links to the full search on dorar.net.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .arabic import normalize

ENDPOINT = os.getenv("TATHABBUT_DORAR_ENDPOINT", "https://dorar.net/dorar_api.json")
SEARCH_URL = "https://dorar.net/hadith/search?q={q}"
USER_AGENT = "Tathabbut/1.0 (+https://tathabbut.vercel.app)"
MAX_BYTES = 2_000_000
MAX_GRADES = 12

LABELS = {
    "الراوي": "narrator", "المحدث": "muhaddith", "المصدر": "source",
    "الصفحة أو الرقم": "ref", "خلاصة حكم المحدث": "grade",
}
_LABEL_RE = re.compile(r"(" + "|".join(re.escape(k) for k in LABELS) + r")\s*:")
_BLOCK_RE = re.compile(r'<div class="hadith"[^>]*>(.*?)</div>\s*<div class="hadith-info">(.*?)</div>', re.S)
_NUMBER_RE = re.compile(r"^\s*\d+\s*[-–.]\s*")


@dataclass
class Record:
    text: str
    narrator: str
    muhaddith: str
    source: str
    ref: str
    grade: str


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def _plain(fragment: str) -> str:
    p = _Plain()
    p.feed(fragment)
    return " ".join(" ".join(p.parts).split())


def parse(body: str) -> list[Record]:
    """Records from a dorar_api.json response (JSON whose 'result' is an HTML fragment)."""
    data = json.loads(body)
    html = ((data or {}).get("ahadith") or {}).get("result") or ""
    out = []
    for text_html, info_html in _BLOCK_RE.findall(html):
        text = _NUMBER_RE.sub("", _plain(text_html)).strip()
        text = re.sub(r"(\s*\.)+\s*$", "", text).strip()          # trailing « . .»
        info = _plain(info_html)
        marks = list(_LABEL_RE.finditer(info))
        fields = {}
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(info)
            fields[LABELS[m.group(1)]] = info[m.end():end].strip(" |")
        if not text or not fields.get("grade") or not fields.get("muhaddith"):
            continue
        narrator = fields.get("narrator", "").strip("[] ")
        out.append(Record(text, "" if narrator in ("", "-") else narrator, fields["muhaddith"],
                          fields.get("source", ""), fields.get("ref", ""), fields["grade"]))
    return out


# --- Reading a ruling -------------------------------------------------------
# Only plain wording is read. Anything else (a remark on one narrator, «تفرد به»,
# «موقوف له حكم الرفع»…) is shown verbatim and counted as unclassified.

_FABRICATED = ("موضوع", "باطل", "كذب", "مختلق", "مختلقه", "المختلقه", "اباطيل", "الاباطيل")
_BASELESS = ("لا اصل له", "ليس له اصل", "لا اصل", "ليس لهذا الحديث اصل", "لم يرد", "ليس حديثا",
             "ليس بحديث", "بلا اسناد", "لا اسناد له")
_WEAK = ("ضعيف", "ضعيفه", "ضعف", "ضعفه", "منكر", "واه", "متروك", "خطا", "اخطا", "لا يصح", "لم يصح", "غير صحيح",
         "ليس بصحيح", "وليس صحيح", "لم يثبت", "لا يثبت", "شاذ", "معلول", "مرسل")
_AUTHENTIC = ("صحيح", "صحيحه", "حسن", "ثابت", "ثبت", "جيد", "قوي", "ثقات", "محفوظ", "صحاح", "صحته", "الصحه")


def _has(text: str, words: tuple[str, ...]) -> bool:
    padded = f" {text} "
    return any(f" {w} " in padded or (" " in w and w in text) for w in words)


def classify(grade: str) -> str:
    """'authentic' | 'weak' | 'fabricated' | 'baseless' | 'unclassified' — from plain wording only."""
    t = normalize(grade)
    # A joined و/ف/ب («وضعفه»، «بالصحة») is read as the word after it. The article is not
    # stripped: «الحسن» is often a narrator's name, not the grade «حسن».
    joined = " ".join(w[1:] if len(w) > 3 and w[0] in "وفب" else w for w in t.split())
    if _has(t, _FABRICATED) or _has(joined, _FABRICATED):
        return "fabricated"
    if _has(t, _BASELESS):
        return "baseless"
    if _has(t, _WEAK) or _has(joined, _WEAK):
        return "weak"
    if _has(t, _AUTHENTIC) or _has(joined, _AUTHENTIC):
        return "authentic"
    return "unclassified"


_CHAIN = ("اسناد", "الاسناد", "اسناده", "اسنادها", "اسانيده", "باسناد", "الوجه", "طريق", "طرقه", "اللفظ")


def chain_only(grade: str) -> bool:
    """«باطل بهذا الإسناد»، «إسناده ضعيف»: a ruling on one chain, not on the hadith itself."""
    t = normalize(grade)
    return _has(t, _CHAIN) and not _has(t, _BASELESS)     # «بلا إسناد» says there is no chain at all


def verdict_of(grades: list[dict]) -> str:
    """A label only when the rulings read clearly agree; otherwise the rulings are shown for review.

    Dorar's search returns the first 15 records, often rulings on single chains or narrators
    («باطل بهذا الإسناد» on a hadith that is in al-Bukhari). So a negative ruling counts only when
    it is about the text, not one chain, and a label needs a clear majority:
      VERIFIED       no ruling against it, not even on one chain, and at least half plainly accept it
      NOT_AUTHENTIC  no ruling accepts it, and at least half (two or more) reject the text itself
      DISPUTED       plain rulings on both sides
      IN_SOURCE      anything else: found in Dorar, rulings listed without a label
    """
    n = len(grades)
    accept = sum(g["class"] == "authentic" for g in grades)
    against = [g for g in grades if g["class"] in ("weak", "fabricated", "baseless")]
    reject = sum(not chain_only(g["grade"]) for g in against)
    if accept and reject:
        return "DISPUTED"
    if accept and not against and accept * 2 >= n:
        return "VERIFIED"
    if not accept and reject >= 2 and reject * 2 >= n:
        return "NOT_AUTHENTIC"
    return "IN_SOURCE"


# --- Fetching ---------------------------------------------------------------

@dataclass
class Lookup:
    ok: bool
    records: list[Record] = field(default_factory=list)
    error: str = ""


class _Cache:
    # Dorar's terms allow caching for performance only, for at most 24–48 hours: 24 hours here.
    def __init__(self, size: int = 2000, ttl: float = 24 * 3600):
        self.size, self.ttl = size, ttl
        self._d: OrderedDict[str, tuple[float, Lookup]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Lookup | None:
        with self._lock:
            hit = self._d.get(key)
            if not hit or time.time() - hit[0] > self.ttl:
                self._d.pop(key, None)
                return None
            self._d.move_to_end(key)
            return hit[1]

    def put(self, key: str, value: Lookup) -> None:
        with self._lock:
            self._d[key] = (time.time(), value)
            self._d.move_to_end(key)
            while len(self._d) > self.size:
                self._d.popitem(last=False)


_cache = _Cache()


class _RateLimit:
    """Dorar's terms set 60 requests a minute per account; stay under it across all users."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._times: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self._lock:
            self._times = [t for t in self._times if now - t < 60]
            if len(self._times) >= self.per_minute:
                return False
            self._times.append(now)
            return True


_limit = _RateLimit(int(os.getenv("TATHABBUT_DORAR_PER_MINUTE", "50")))


def query_text(claim: str) -> str:
    return normalize(claim)


def search_url(claim: str) -> str:
    return SEARCH_URL.format(q=quote(claim.strip()))


def fetch(claim: str, timeout: float = 4.0, opener=urlopen) -> Lookup:
    """One request to Dorar's API; failures are reported, never retried."""
    q = query_text(claim)
    key = hashlib.sha1(q.encode()).hexdigest()
    cached = _cache.get(key)
    if cached is not None:
        return cached
    if not _limit.allow():
        return Lookup(False, error="RateLimited")
    url = ENDPOINT + "?" + urlencode({"skey": q})
    try:
        req = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
        with opener(req, timeout=timeout) as resp:
            body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("response too large")
        result = Lookup(True, parse(body.decode("utf-8")))
    except Exception as exc:  # network, HTTP, JSON: the card says the lookup could not be done
        return Lookup(False, error=type(exc).__name__)
    _cache.put(key, result)
    return result


# --- From Dorar records to a judgement ----------------------------------------

LIVE_NOTE = ("نتيجة من البحث المباشر في الدرر السنية: الأحكام منقولة كما هي منسوبة لأصحابها، "
             "وتخص أول نتائج البحث فقط، وقد تتعلق بروايات أو أسانيد مختلفة؛ افتح البحث في الدرر للاطلاع على التفصيل.")
SIMILAR_NOTE = ("أقرب نص في نتائج الدرر السنية يختلف في ألفاظه؛ تُعرض أحكامه ولا تُنقل إلى النص المدخل قبل مراجعة الفروق.")
NOT_FOUND_NOTE = "وبُحث عنه مباشرة في الدرر السنية فلم يُعثر في أول نتائج البحث على نص يطابقه."
UNAVAILABLE_NOTE = "تعذّر الوصول إلى الدرر السنية الآن للبحث المباشر؛ أعد المحاولة لاحقاً أو ابحث عنه في موقع الدرر."


def _grade(r: Record) -> dict:
    return {"muhaddith": r.muhaddith, "source": r.source, "ref": r.ref, "grade": r.grade,
            "class": classify(r.grade), "narrator": r.narrator}


def judge_live(claim_text: str, lookup: Lookup, th):
    """Judgement for a hadith claim from Dorar records, or None when nothing is close enough."""
    from .align import align
    from .index import Doc, Hit
    from .judge import Candidate, Judgement

    if not lookup.ok or not lookup.records:
        return None
    scored = []
    for i, r in enumerate(lookup.records):
        al = align(claim_text, r.text, stemmed=False, preserve_negation=True, leading_conjunction=True)
        scored.append((al, r, i))
    exact = [(al, r) for al, r, _ in scored if al.exact and al.claim_coverage == 1]
    url = search_url(claim_text)

    def doc_for(r: Record, grades: list[dict]) -> Doc:
        did = "dorar-live-" + hashlib.sha1(r.text.encode()).hexdigest()[:10]
        return Doc(id=did, kind="hadith", text=r.text, ref={"narrator": r.narrator, "live": True},
                   grades=grades, url=url, verified=True)

    if exact:
        seen, grades = set(), []
        for _, r in exact:
            k = (r.muhaddith, r.source, r.ref)
            if k not in seen:
                seen.add(k)
                grades.append(_grade(r))
        grades = grades[:MAX_GRADES]
        # The record shown is the shortest one that contains the quotation.
        al, r = min(exact, key=lambda x: len(x[1].text))
        doc = doc_for(r, grades)
        code = verdict_of(grades)
        notes = [LIVE_NOTE]
        if code == "IN_SOURCE":
            notes.insert(0, "وُجد النص في الدرر السنية، وأحكامه المعروضة لا تتفق على حكم واضح أو تخص أسانيد بعينها؛ "
                            "تُعرض كما هي دون استنتاج حكم منها.")
        return Judgement(code, Candidate(Hit(doc, 0.0, None, None), al, doc), notes=notes)

    al, r, _ = max(scored, key=lambda x: (round(x[0].content_coverage, 3), x[0].claim_coverage, -x[2]))
    if al.content_coverage >= th.hadith_review_min:
        doc = doc_for(r, [_grade(r)])
        return Judgement("NEEDS_REVIEW", Candidate(Hit(doc, 0.0, None, None), al, doc),
                         notes=[SIMILAR_NOTE, LIVE_NOTE])
    return None
