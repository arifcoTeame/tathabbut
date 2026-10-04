// Mirrors backend/app/schemas.py

export type VerdictCode =
  | "VERIFIED"
  | "NOT_AUTHENTIC"
  | "ALTERED"
  | "NO_ORIGIN"
  | "DISPUTED"
  | "REFER"
  | "NEEDS_REVIEW";

export interface Grade {
  muhaddith: string;
  source: string;
  ref: string;
  grade: string;
  class: string;
  /** e.g. «بلفظ مقارب» when the source's wording differs slightly from the record text */
  note?: string;
}

export interface SourceRef {
  surah?: number;
  ayah?: number;
  ayah_end?: number;
  surah_name?: string;
  narrator?: string;
  /** full wording of the cited entry in the source (hadith) when the record is a popular fragment */
  context?: string;
}

export interface Source {
  id: string;
  kind: "quran" | "hadith";
  text: string;
  ref: SourceRef;
  url: string;
  verified: boolean;
}

export type DiffOp =
  | { op: "equal"; text: string }
  | { op: "added"; claim: string }
  | { op: "missing"; source: string }
  | { op: "changed"; claim: string; source: string };

export interface Evidence {
  claim_coverage: number;
  content_coverage: number;
  span_coverage: number;
  similarity: number;
  retrieval_fused: number;
  bm25_rank: number | null;
  dense_rank: number | null;
}

export interface Claim {
  id: number;
  text: string;
  type_hint: "quran" | "hadith" | "personal" | "unknown";
  level: "A" | "B" | "C" | "D";
  verdict: { code: VerdictCode; label_ar: string };
  source: Source | null;
  grades: Grade[];
  diff: DiffOp[];
  evidence: Evidence | null;
  closest: (Source & { grades: Grade[]; content_coverage: number; note: string }) | null;
  alternatives: { id: string; ref: SourceRef; url: string }[];
  notes: string[];
  explanation: { kind: string; generated: boolean; text: string } | null;
}

export interface IndexStats {
  embedder: string;
  docs: number;
  quran: number;
  hadith: number;
  verified_docs: number;
  quran_complete: boolean;
}

export interface VerifyResponse {
  claims: Claim[];
  summary: Record<VerdictCode, number>;
  index: IndexStats;
  disclaimer: string;
  engine_version: string;
  elapsed_ms: number;
}
