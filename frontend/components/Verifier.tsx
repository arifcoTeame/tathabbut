"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { IndexStats, VerifyResponse } from "@/lib/types";
import { VERDICT_META, VERDICT_ORDER } from "@/lib/verdicts";
import ClaimCard from "./ClaimCard";

const MAX_CHARS = 4000;

function claimsCount(n: number): string {
  if (n === 1) return "ادعاء واحد";
  if (n === 2) return "ادعاءان";
  if (n >= 3 && n <= 10) return `${n} ادعاءات`;
  return `${n} ادعاءً`;
}

const EXAMPLES: { label: string; text: string }[] = [
  {
    label: "منشور بثلاثة ادعاءات",
    text:
      "قال رسول الله ﷺ: «اطلبوا العلم ولو في الصين». وقال تعالى: ﴿ومن يتوكل على الله فهو حسبه ونعم الوكيل﴾، " +
      "فلا تخف من المستقبل. وسألني أحد المتابعين: «أنا مقيم في بلد غير مسلم وزوجتي تطلب الطلاق، هل يجوز لي رفض طلبها؟» " +
      "فأجبته بأن ذلك لا يجوز.",
  },
  { label: "حديث منتشر", text: "حب الوطن من الإيمان" },
  { label: "آية بكلمة مستبدلة", text: "قال تعالى: ﴿لا يكلف الله نفسا إلا طاقتها﴾" },
  { label: "آية منسوبة للنبي ﷺ", text: "قال النبي ﷺ: «قل هو الله أحد الله الصمد»" },
  { label: "حديث صحيح", text: "قال رسول الله ﷺ: «لا يؤمن أحدكم حتى يحب لأخيه ما يحب لنفسه»" },
];

type Status =
  | { state: "checking"; waking: boolean }
  | { state: "up"; stats: IndexStats }
  | { state: "down" };

function IndexStatus({ status, onRetry }: { status: Status; onRetry: () => void }) {
  if (status.state === "checking")
    return (
      <span className="status">
        <span className="dot pulse" />
        {status.waking ? "المحرك يستيقظ… قد يستغرق ذلك دقيقة" : "جارٍ الاتصال بالمحرك…"}
      </span>
    );
  if (status.state === "down")
    return (
      <span className="status">
        <span className="dot down" />المحرك غير متصل
        <button className="btn-ghost" onClick={onRetry}>إعادة المحاولة</button>
      </span>
    );
  const s = status.stats;
  return (
    <span className="status" title={`نموذج التضمين: ${s.embedder}`}>
      <span className="dot ok" />
      {s.quran_complete ? `المصحف كاملاً (${s.quran.toLocaleString("ar")} آية)` : `عينة قرآنية (${s.quran} آية)`}
      {" · "}
      {s.hadith} حديثاً مفهرساً
    </span>
  );
}

export default function Verifier() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VerifyResponse | null>(null);
  const [status, setStatus] = useState<Status>({ state: "checking", waking: false });
  const resultsRef = useRef<HTMLDivElement>(null);

  // Doubles as a wake-up call for a sleeping free-tier backend.
  const connect = useCallback(() => {
    setStatus({ state: "checking", waking: false });
    const slow = setTimeout(() => setStatus((s) => (s.state === "checking" ? { ...s, waking: true } : s)), 3000);
    fetch("/api/stats")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((stats: IndexStats) => setStatus({ state: "up", stats }))
      .catch(() => setStatus({ state: "down" }))
      .finally(() => clearTimeout(slow));
  }, []);

  useEffect(() => connect(), [connect]);

  async function verify(input = text) {
    const value = input.trim();
    if (value.length < 2 || value.length > MAX_CHARS || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: value }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "تعذّر إتمام التحقق.");
      setResult(data as VerifyResponse);
      if (status.state !== "up") connect();
      requestAnimationFrame(() => resultsRef.current?.focus());
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "تعذّر إتمام التحقق.");
    } finally {
      setLoading(false);
    }
  }

  const over = text.length > MAX_CHARS;

  return (
    <>
      <header className="topbar">
        <img src="/logo.png" alt="تثبّت — محرّك التحقق المُسنَد للمحتوى الإسلامي" />
        <IndexStatus status={status} onRetry={connect} />
      </header>

      <section className="hero">
        <h1>تحقّق قبل أن تنشر</h1>
        <p>
          الصق منشوراً أو نصاً يتضمن أحاديث أو آيات أو أقوالاً منسوبة، فيستخرج «تثبّت» كل ادعاء ويطابقه
          بالمصادر المعتمدة، ويصدر لكل ادعاء حكماً مُسنَداً بقواعد حتمية لا يولّدها النموذج اللغوي.
        </p>
      </section>

      <div className="grid">
        <section className="panel sticky" aria-label="النص المراد التحقق منه">
          <h2>
            <label htmlFor="post">النص المراد التحقق منه</label>
            {text && (
              <button className="btn-ghost" onClick={() => { setText(""); setResult(null); setError(null); }}>
                مسح
              </button>
            )}
          </h2>
          <textarea
            id="post"
            className="post"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) verify();
            }}
            placeholder="الصق هنا منشوراً أو حديثاً أو آية…"
          />
          <div className="row">
            <span className={`count ${over ? "over" : ""}`}>
              {text.length.toLocaleString("ar")} / {MAX_CHARS.toLocaleString("ar")} حرف
            </span>
            <span className="kbd">⌘ + Enter</span>
            <button className="btn" onClick={() => verify()} disabled={loading || over || text.trim().length < 2}>
              {loading ? "جارٍ التحقق…" : "تثبّت الآن"}
            </button>
          </div>
          <div className="examples">
            <span className="label">أمثلة للتجربة:</span>
            {EXAMPLES.map((ex) => (
              <button
                key={ex.label}
                className="btn-ghost"
                onClick={() => { setText(ex.text); verify(ex.text); }}
              >
                {ex.label}
              </button>
            ))}
          </div>
        </section>

        <section aria-live="polite" aria-busy={loading} tabIndex={-1} ref={resultsRef} style={{ outline: "none" }}>
          {error && <div className="error" role="alert">{error}</div>}
          {loading && <div className="loading">جارٍ استخراج الادعاءات ومطابقتها بالمصادر…</div>}
          {!loading && !error && !result && (
            <div className="empty">
              ستظهر هنا «بطاقة تثبّت» لكل ادعاء: الحكم، والنص المعتمد، والمصدر، والفروق كلمة بكلمة.
            </div>
          )}
          {!loading && result && (
            <>
              <h2 className="sr-only">نتائج التحقق</h2>
              <div className="summary">
                {VERDICT_ORDER.map((code) => (
                  <span key={code} className={`chip ${result.summary[code] ? "" : "zero"}`}>
                    {VERDICT_META[code].label}
                    <b>{result.summary[code] ?? 0}</b>
                  </span>
                ))}
                <span className="meta-line">
                  {claimsCount(result.claims.length)} · {result.elapsed_ms} ms
                </span>
              </div>
              {result.claims.length === 0 ? (
                <div className="empty">لم يُعثر على ادعاءات شرعية قابلة للتحقق في هذا النص.</div>
              ) : (
                <div className="cards">
                  {result.claims.map((c) => (
                    <ClaimCard key={c.id} claim={c} />
                  ))}
                </div>
              )}
            </>
          )}
        </section>
      </div>

      <footer className="footer">
        <span>
          تثبّت أداة مدعومة بالذكاء الاصطناعي ولا تُغني عن المختص · النص الشرعي منسوخ من المصادر المعتمدة والدرجات
          منقولة عن المحدّثين · لا تُحفظ النصوص المُدخلة.
        </span>
        <a href="https://github.com/arifcoTeame/tathabbut/issues/new" target="_blank" rel="noopener noreferrer">
          الإبلاغ عن خطأ في حكم ↗
        </a>
      </footer>
    </>
  );
}
