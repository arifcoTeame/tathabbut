from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class VerifyRequest(BaseModel):
    text: str = Field(..., min_length=2, description="النص أو المنشور المراد التحقق منه")

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("أدخل نصاً من حرفين على الأقل بعد إزالة المسافات.")
        return value


class Verdict(BaseModel):
    code: str
    label_ar: str


class SourceOut(BaseModel):
    id: str
    kind: str
    text: str
    ref: dict
    url: str
    verified: bool


class Evidence(BaseModel):
    claim_coverage: float
    content_coverage: float
    span_coverage: float
    similarity: float
    retrieval_fused: float
    bm25_rank: int | None
    dense_rank: int | None


class ClaimOut(BaseModel):
    id: int
    text: str
    type_hint: str
    level: str
    verdict: Verdict
    source: SourceOut | None = None
    grades: list[dict] = []
    diff: list[dict] = []
    evidence: Evidence | None = None
    closest: dict | None = None
    alternatives: list[dict] = []
    notes: list[str] = []
    explanation: dict | None = None


class VerifyResponse(BaseModel):
    claims: list[ClaimOut]
    summary: dict[str, int]
    index: dict
    disclaimer: str
    engine_version: str
    elapsed_ms: int
