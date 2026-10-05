import type { Claim } from "@/lib/types";
import { LEVEL_LABEL, TYPE_LABEL, pct, verseLabel } from "@/lib/verdicts";
import { DORAR_SEARCH_LABEL, SIMILAR_TEXT, outcome } from "@/lib/advice";
import DiffView from "./DiffView";

const dorarSearch = (q: string) => `https://dorar.net/hadith/search?q=${encodeURIComponent(q)}`;
/** Only a link to the entry itself (dorar.net/h/…) may be called "open the result"; anything else is a search. */
const isDorarEntry = (u?: string | null) => !!u && u.startsWith("https://dorar.net/h/");

function sourceButton(kind: string | undefined, url: string | undefined, similar: boolean): string {
  if (kind === "quran") return "فتح الآية في Quranpedia";
  if (!isDorarEntry(url)) return similar ? "البحث عن النص المشابه في الدرر السنية" : "البحث عن النص في الدرر السنية";
  return similar ? "فتح الحديث المشابه في الدرر السنية" : "فتح النتيجة في الدرر السنية";
}

/** One card: the practical result first, then the details it rests on. */
export default function ClaimCard({ claim }: { claim: Claim }) {
  const o = outcome(claim);
  const src = claim.source;
  const code = claim.verdict.code;
  const showDiff = claim.diff.length > 0 && claim.diff.some((d) => d.op !== "equal");
  const similar = code === "NEEDS_REVIEW" && !!src;          // a close text, not an exact match
  const hadithReview = src?.kind === "hadith" && code === "NEEDS_REVIEW";
  const misattributed = claim.type_hint === "hadith" && src?.kind === "quran";
  const searchDorar = !src && code === "NO_ORIGIN" && claim.type_hint !== "quran";
  // The list of related verses is shown as links below; its sentence would repeat it.
  const notes = claim.notes.filter((n) =>
    code === "NO_ORIGIN" ? n.startsWith("كلمة واحدة") : !n.startsWith("آيات أخرى تشترك"));

  return (
    <article className="card" aria-labelledby={`claim-${claim.id}`}>
      <div className={`badge tone-${o.tone}`}>
        <span className="b-icon" aria-hidden>{o.icon}</span>
        {o.label}
        <small>{o.hint}</small>
        {misattributed && <span className="flag">النص آية لا حديث</span>}
      </div>

      <div>
        <p className="c-claim" id={`claim-${claim.id}`}>
          <span className="lbl">النص المدخل</span>«{claim.text}»
        </p>

        <div className={`verdict-box tone-${o.tone}`}>
          <p className="v-summary">{o.summary}</p>
          <p className="v-advice"><b>الخلاصة: </b>{o.advice}</p>
          {o.note && <p className="v-note">{o.note}</p>}
          {(src?.url || searchDorar) && (
            <a
              className="btn-source"
              href={src?.url || dorarSearch(claim.text)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {src ? sourceButton(src.kind, src.url, similar) : DORAR_SEARCH_LABEL} ↗
            </a>
          )}
        </div>

        {src && (
          <>
            <blockquote className={`quote ${similar ? "similar" : ""}`}>
              {similar && <span className="similar-note">{SIMILAR_TEXT}</span>}
              <span className="lbl">
                {src.kind === "quran"
                  ? similar ? "النص القرآني المشابه (Quranpedia)" : "النص القرآني المعتمد (Quranpedia)"
                  : similar ? "النص المشابه في قاعدة المنصة، بلفظه المنقول من الدرر السنية" : "لفظ الحديث كما نُقل من الدرر السنية"}
              </span>
              {src.kind === "quran" ? `﴿${src.text}﴾` : src.text}
              {src.kind === "hadith" && src.ref.context && src.ref.context !== src.text && (
                <span className="ctx">
                  <span className="lbl">الموضع كاملاً كما تعرضه الدرر السنية</span>
                  {src.ref.context}
                </span>
              )}
            </blockquote>
            <div className="src">
              {src.kind === "quran" ? <span>{verseLabel(src.ref)}</span> : src.ref.narrator ? <span>الراوي: {src.ref.narrator}</span> : null}
              {!src.verified && <span className="tag warn">سجل تجريبي لم يُراجع بعد</span>}
            </div>
          </>
        )}

        {claim.grades.length > 0 && (
          <>
            {hadithReview && (
              <p className="coverage-note">الأحكام التالية تخص لفظ المصدر؛ لا تُنقل إلى النص المدخل قبل مراجعة الفروق.</p>
            )}
            <ul className="grades" aria-label="حكم الحديث كما في الدرر السنية">
              {claim.grades.map((g, i) => (
                <li key={i}>
                  <span className="g-label">الحكم:</span> <b>{g.grade}</b>
                  <span className="g-meta"> — المحدّث: {g.muhaddith} · المصدر: {g.source}{g.ref ? ` · الرقم أو الصفحة: ${g.ref}` : ""}</span>
                  {g.note && <span className="tag">{g.note}</span>}
                  {g.url && (
                    <a className="inline-link" href={g.url} target="_blank" rel="noopener noreferrer">
                      فتح هذا الحكم في الدرر السنية ↗
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {showDiff && (
          <div style={{ marginTop: 8 }}>
            <div className="c-head">موضع الاختلاف كلمة بكلمة</div>
            <DiffView ops={claim.diff} sourceKind={src?.kind} />
          </div>
        )}

        {claim.alternatives.length > 0 && (
          <div className="src" style={{ marginTop: 8 }}>
            <span>{code === "VERIFIED" ? "يتكرر النص نفسه في:" : "آيات أخرى تشترك في ألفاظ النص:"}</span>
            {claim.alternatives.map((a) => (
              <a key={a.id} href={a.url} target="_blank" rel="noopener noreferrer">
                {verseLabel(a.ref).replace("سورة ", "")}
              </a>
            ))}
          </div>
        )}

        {claim.closest && (
          <blockquote className="quote muted similar">
            <span className="similar-note">{SIMILAR_TEXT} لا يُبنى عليه حكم.</span>
            <span className="lbl">{claim.closest.kind === "quran" ? "أقرب آية في Quranpedia" : "أقرب حديث في قاعدة المنصة"}</span>
            {claim.closest.text}
            {claim.closest.url && (
              <a className="inline-link" href={claim.closest.url} target="_blank" rel="noopener noreferrer">
                {sourceButton(claim.closest.kind, claim.closest.url, true)} ↗
              </a>
            )}
          </blockquote>
        )}

        {notes.length > 0 && (
          <ul className="notes">
            {notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        )}

        <details className="evidence">
          <summary>تفاصيل تقنية</summary>
          <dl>
            <dt>نوع المدخل</dt><dd>{TYPE_LABEL[claim.type_hint]} · {LEVEL_LABEL[claim.level]}</dd>
            {claim.evidence && (
              <>
                <dt>تغطية ألفاظ النص</dt><dd>{pct(claim.evidence.claim_coverage)}</dd>
                <dt>تغطية الكلمات الجوهرية</dt><dd>{pct(claim.evidence.content_coverage)}</dd>
                <dt>تطابق المقطع في المصدر</dt><dd>{pct(claim.evidence.span_coverage)}</dd>
                <dt>ترتيب الاسترجاع (BM25 / TF-IDF)</dt>
                <dd>{claim.evidence.bm25_rank ?? "—"} / {claim.evidence.dense_rank ?? "—"}</dd>
              </>
            )}
          </dl>
          {claim.explanation && <p className="gen">{claim.explanation.text}</p>}
        </details>
      </div>
    </article>
  );
}
