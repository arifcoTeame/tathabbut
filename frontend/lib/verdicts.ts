import type { Claim, SourceRef, VerdictCode } from "./types";

export const VERDICT_ORDER: VerdictCode[] = [
  "VERIFIED",
  "NOT_AUTHENTIC",
  "ALTERED",
  "NO_ORIGIN",
  "DISPUTED",
  "REFER",
  "NEEDS_REVIEW",
  "OUT_OF_SCOPE",
];

export const VERDICT_META: Record<VerdictCode, { label: string; hint: string; tone: string }> = {
  VERIFIED: { label: "مطابق للمصدر", hint: "آية مطابقة أو حديث صحيح/حسن بحسب الدرر السنية", tone: "verified" },
  NOT_AUTHENTIC: { label: "ضعيف أو موضوع", hint: "بحسب حكم الدرر السنية", tone: "weak" },
  ALTERED: { label: "يختلف عن النص القرآني", hint: "النص المعتمد في Quranpedia", tone: "altered" },
  NO_ORIGIN: { label: "لم يُعثر عليه", hint: "ضمن قاعدة الأحاديث الحالية في المنصة · لا يعني الحكم بالصحة أو الضعف", tone: "noorigin" },
  DISPUTED: { label: "حكم مختلف فيه", hint: "بحسب الدرر السنية", tone: "disputed" },
  REFER: { label: "إحالة إلى مختص", hint: "حالة شخصية", tone: "refer" },
  NEEDS_REVIEW: { label: "يحتاج إلى تحقق إضافي", hint: "نتيجة مشابهة وليست مطابقة", tone: "review" },
  OUT_OF_SCOPE: { label: "سؤال عام", hint: "خارج نطاق التحقق", tone: "refer" },
};

export const TYPE_LABEL: Record<Claim["type_hint"], string> = {
  quran: "آية",
  hadith: "حديث منسوب",
  personal: "سؤال شخصي",
  unknown: "ادعاء",
};

export const LEVEL_LABEL: Record<Claim["level"], string> = {
  A: "المستوى (أ): نص أصلي",
  B: "المستوى (ب): شرح وتعريف",
  C: "المستوى (ج): مسألة اجتهادية",
  D: "المستوى (د): فتوى أو حالة شخصية",
};

export function verseLabel(ref: SourceRef): string {
  if (!ref.surah_name) return "";
  return ref.ayah_end
    ? `سورة ${ref.surah_name}، الآيات ${ref.ayah}–${ref.ayah_end}`
    : `سورة ${ref.surah_name}، الآية ${ref.ayah}`;
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
