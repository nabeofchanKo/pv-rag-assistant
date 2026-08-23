"""Phase 4d: past-case precedent (structured per-(drug, PT) lookup).

Cross-case consistency: for each adverse event in a new case, surface how past
**approved** cases judged the same MedDRA PT under the same drug, and flag where
the current draft disagrees with the precedent majority. This is **advisory** —
it never changes a verdict (the human decides); contrast the IME list, which
fires criterion 6 deterministically. See ADR 0009.

Structured lookup (not vector similarity) is deliberate: consistency is a
per-(drug, PT) question, and dense vectors are weak on exact/variant matches
(same lesson as ADR 0003). A narrative-similarity RAG layer is a later slice.

Records live as JSON: a curated **seed** dir (tracked) + a **runtime** dir where
approved cases are auto-saved. Both are read; the in-memory index updates on save
so a just-approved case is precedent for the next one, in-process.
"""

import json
import logging
import re
import threading
from collections import Counter
from pathlib import Path

from app.schemas import (
    CausalityAssessment,
    DrugExpectedness,
    EventPrecedent,
    MeddraCoding,
    PastCaseEvent,
    PastCaseRecord,
    SeriousnessAssessment,
    TriageResult,
)

logger = logging.getLogger(__name__)


def record_from_result(result: TriageResult) -> PastCaseRecord:
    """Build a compact precedent record from an approved triage result."""
    drugs = [p.name for p in result.product_match.matched_products]
    ser = {s.term: s.verdict for s in result.seriousness}
    cau = {c.term: c.verdict for c in result.causality}
    # term -> {drug: expectedness verdict}
    exp: dict[str, dict[str, str]] = {}
    for de in result.expectedness:
        for a in de.assessments:
            exp.setdefault(a.term, {})[de.drug_name] = a.verdict

    events: list[PastCaseEvent] = []
    for i, ae in enumerate(result.extraction.adverse_events):
        coding = result.meddra[i] if i < len(result.meddra) else None
        events.append(
            PastCaseEvent(
                term=ae.term,
                pt_code=coding.pt_code if coding else None,
                pt_name=coding.pt_name_ja if coding else None,
                seriousness=ser.get(ae.term),
                causality=cau.get(ae.term),
                expectedness=exp.get(ae.term, {}),
            )
        )
    date = result.review.reviewed_at.date().isoformat() if result.review else None
    return PastCaseRecord(
        case_id=result.document_name or "unknown",
        date=date,
        drugs=drugs,
        reviewer=result.review.reviewer if result.review else None,
        events=events,
    )


def _majority(counts: dict[str, int]) -> str | None:
    return max(counts, key=counts.get) if counts else None


class PrecedentService:
    """Index approved past cases by (drug, pt_code); summarize + persist."""

    def __init__(self, seed_dir: str, runtime_dir: str) -> None:
        self.seed_dir = Path(seed_dir)
        self.runtime_dir = Path(runtime_dir)
        self._lock = threading.Lock()
        self._index: dict[tuple[str, str], list[dict]] = {}
        self._load_all()

    def _load_all(self) -> None:
        self._index = {}
        n = 0
        for directory in (self.seed_dir, self.runtime_dir):
            if not directory.exists():
                continue
            for f in sorted(directory.glob("*.json")):
                try:
                    rec = PastCaseRecord(**json.loads(f.read_text(encoding="utf-8")))
                except Exception as e:  # skip a malformed record, don't crash startup
                    logger.warning("Skipping past-case file %s: %s", f, e)
                    continue
                self._index_record(rec)
                n += 1
        logger.info("Loaded %d past cases (%d index keys)", n, len(self._index))

    def _index_record(self, rec: PastCaseRecord) -> None:
        for ev in rec.events:
            if not ev.pt_code:
                continue
            for drug in rec.drugs:
                self._index.setdefault((drug, ev.pt_code), []).append(
                    {
                        "case_id": rec.case_id,
                        "seriousness": ev.seriousness,
                        "causality": ev.causality,
                        "expectedness": ev.expectedness.get(drug),
                    }
                )

    def summarize(
        self,
        drugs: list[str],
        meddra: list[MeddraCoding],
        seriousness: list[SeriousnessAssessment],
        causality: list[CausalityAssessment],
        expectedness: list[DrugExpectedness],
    ) -> list[EventPrecedent]:
        """One EventPrecedent per adverse event (aligned to adverse_events order)."""
        ser_now = {s.term: s.verdict for s in seriousness}
        cau_now = {c.term: c.verdict for c in causality}

        out: list[EventPrecedent] = []
        for coding in meddra:
            pt = coding.pt_code
            entries = []
            if pt:
                for drug in drugs:
                    entries.extend(self._index.get((drug, pt), []))

            # seriousness / causality are event-level -> dedupe by case so two
            # matched drugs from the same past case don't double-count.
            by_case = {e["case_id"]: e for e in entries}
            ser_counts = Counter(
                e["seriousness"] for e in by_case.values() if e["seriousness"]
            )
            cau_counts = Counter(
                e["causality"] for e in by_case.values() if e["causality"]
            )
            # expectedness is per (drug, PT) -> keep all entries.
            exp_counts = Counter(e["expectedness"] for e in entries if e["expectedness"])

            conflicts: list[str] = []
            if ser_counts and _majority(ser_counts) != ser_now.get(coding.term):
                conflicts.append("seriousness")
            if cau_counts and _majority(cau_counts) != cau_now.get(coding.term):
                conflicts.append("causality")

            out.append(
                EventPrecedent(
                    term=coding.term,
                    pt_code=pt,
                    n_cases=len(by_case),
                    seriousness=dict(ser_counts),
                    causality=dict(cau_counts),
                    expectedness=dict(exp_counts),
                    case_ids=sorted(by_case.keys()),
                    conflicts=conflicts,
                )
            )
        return out

    def save(self, record: PastCaseRecord) -> Path:
        """Persist an approved case and refresh the in-memory index."""
        with self._lock:
            self.runtime_dir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^0-9A-Za-z._-]", "_", record.case_id) or "case"
            path = self.runtime_dir / f"{safe}.json"
            path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
            self._load_all()  # rebuild (filename == case_id -> overwrite dedupes)
            return path
