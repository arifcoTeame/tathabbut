import type { Claim, SourceRef, VerdictCode } from "./types";

export const VERDICT_ORDER: VerdictCode[] = [
  "VERIFIED",
  "NOT_AUTHENTIC",
  "ALTERED",
  "NO_ORIGIN",
  "DISPUTED",
  "REFER",
  "NEEDS_REVIEW",
];

export const VERDICT_META: Record<VerdictCode, { label: string; hint: string; tone: string }> = {
  VERIFIED: { label: "موثّق", hint: "مطابق للمصدر المعتمد", tone: "verified" },
  NOT_AUTHENTIC: { label: "لا يصح", hint: "بدرجة منقولة عن المحدّثين", tone: "weak" },
  ALTERED: { label: "مُحرَّف", hint: "يختلف عن نص المصحف", tone: "altered" },
  NO_ORIGIN: { label: "لم يُعثر عليه", hint: "ضمن الفهرس الحالي · يلزم بحث أوسع", tone: "noorigin" },
  DISPUTED: { label: "خلافي", hint: "لا يُعرض بصيغة القطع", tone: "disputed" },
  REFER: { label: "إحالة", hint: "حالة شخصية · المستوى (د)", tone: "refer" },
  NEEDS_REVIEW: { label: "يتطلب مزيد تحقق", hint: "مطابقة غير كافية للحكم", tone: "review" },
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
