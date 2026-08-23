"""Phase 4e: the influence layer — fold past data into verdicts, or annotate.

One mode toggle governs BOTH past-data sources:

* ``applied`` (default) — history is authoritative:
  - **IME** (past *feedback*, an explicit prior human decision that a PT is
    medically important) → fire E2A criterion 6 → **重篤** deterministically, citing
    the PT + its provenance.
  - **precedent** (past *cases*, aggregate statistics) → a **safe-side nudge only**:
    if the past majority is stricter than the fresh verdict, bump it up — but only
    to **要確認** (surface for the human), never straight to 重篤, and **never a
    downgrade**. Causality: a fresh 否定できる against a past majority that kept the
    event in scope → 否定できない (stay in scope).
* ``advisory`` — history changes nothing; the same signals are recorded as notes
  ("以前のFB(IME昇格)では…", "過去症例では 重篤2件") for the reviewer.

Keeping this out of the assessment services means the fresh judgment and the
history-adjusted judgment are directly comparable (advisory output == fresh). See
ADR 0010 (and ADR 0004 follow-up: IME criterion 6 moved here).
"""

from app.schemas import (
    CausalityAssessment,
    DrugExpectedness,
    EventPrecedent,
    InfluenceItem,
    MeddraCoding,
    SeriousnessAssessment,
    SeriousnessHit,
)
from app.services.ime import ImeReference

# Higher = more serious / more safety-relevant to report.
_SER_SEVERITY = {"非重篤": 0, "要確認": 1, "重篤": 2}


def _fmt_counts(d: dict[str, int]) -> str:
    return "／".join(f"{v}{n}件" for v, n in d.items())


class InfluenceService:
    def __init__(self, ime: ImeReference) -> None:
        self.ime = ime

    def apply(
        self,
        mode: str,
        meddra: list[MeddraCoding],
        seriousness: list[SeriousnessAssessment],
        causality: list[CausalityAssessment],
        expectedness: list[DrugExpectedness],
        precedent: list[EventPrecedent],
    ) -> tuple[
        list[SeriousnessAssessment],
        list[CausalityAssessment],
        list[DrugExpectedness],
        list[InfluenceItem],
        str,
    ]:
        mode = "advisory" if mode == "advisory" else "applied"
        prec_by_term = {ep.term: ep for ep in precedent}
        pt_by_term = {c.term: c for c in meddra}

        if mode == "advisory":
            return (
                seriousness,
                causality,
                expectedness,
                self._notes(seriousness, causality, meddra, prec_by_term),
                mode,
            )

        ser = list(seriousness)
        cau = list(causality)
        items: list[InfluenceItem] = []

        # 1) IME (past feedback) -> criterion 6 = 重篤 (deterministic).
        for i, s in enumerate(ser):
            coding = pt_by_term.get(s.term)
            if not coding or not self.ime.contains(coding.pt_code):
                continue
            if s.verdict == "重篤" and any(h.criterion == "医学的に重要" for h in s.hits):
                continue
            quote = f"IME該当PT: {coding.pt_name_ja}（{coding.pt_code}）"
            prov = self.ime.note(coding.pt_code)
            if prov:
                quote += f" ／ {prov}"
            new_hits = list(s.hits) + [
                SeriousnessHit(criterion="医学的に重要", evidence_quote=quote, source="IME")
            ]
            items.append(
                InfluenceItem(
                    axis="seriousness", term=s.term, source="IME", applied=True,
                    from_verdict=s.verdict, to_verdict="重篤", note=quote,
                )
            )
            ser[i] = s.model_copy(update={"verdict": "重篤", "hits": new_hits})

        # 2) precedent (past cases) -> safe-side nudge, capped at 要確認.
        for i, s in enumerate(ser):
            ep = prec_by_term.get(s.term)
            if not ep or not ep.seriousness:
                continue
            majority = max(ep.seriousness, key=ep.seriousness.get)
            if _SER_SEVERITY.get(majority, 0) > _SER_SEVERITY.get(s.verdict, 0):
                target = "要確認" if _SER_SEVERITY[s.verdict] < 1 else s.verdict
                if target != s.verdict:
                    items.append(
                        InfluenceItem(
                            axis="seriousness", term=s.term, source="precedent", applied=True,
                            from_verdict=s.verdict, to_verdict=target,
                            note=f"過去症例では {_fmt_counts(ep.seriousness)} → 安全側で要確認",
                        )
                    )
                    ser[i] = s.model_copy(update={"verdict": target})

        # 3) causality: fresh 否定できる vs a past majority that kept it in scope.
        for i, c in enumerate(cau):
            ep = prec_by_term.get(c.term)
            if not ep or not ep.causality or c.verdict != "否定できる":
                continue
            majority = max(ep.causality, key=ep.causality.get)
            if majority in ("否定できない", "評価不能"):
                items.append(
                    InfluenceItem(
                        axis="causality", term=c.term, source="precedent", applied=True,
                        from_verdict=c.verdict, to_verdict="否定できない",
                        note=f"過去症例では {_fmt_counts(ep.causality)} → 安全側でスコープ維持",
                    )
                )
                cau[i] = c.model_copy(update={"verdict": "否定できない"})

        return ser, cau, expectedness, items, mode

    def _notes(
        self,
        seriousness: list[SeriousnessAssessment],
        causality: list[CausalityAssessment],
        meddra: list[MeddraCoding],
        prec_by_term: dict[str, EventPrecedent],
    ) -> list[InfluenceItem]:
        """Advisory mode: record what history *would* say, without changing verdicts."""
        items: list[InfluenceItem] = []
        for coding in meddra:
            if self.ime.contains(coding.pt_code):
                prov = self.ime.note(coding.pt_code)
                note = f"以前のFB（IME昇格）では医学的に重要: {coding.pt_name_ja}（{coding.pt_code}）"
                if prov:
                    note += f" ／ {prov}"
                items.append(
                    InfluenceItem(axis="seriousness", term=coding.term, source="IME",
                                  applied=False, note=note)
                )
        for ep in prec_by_term.values():
            if ep.n_cases and ep.seriousness:
                items.append(
                    InfluenceItem(axis="seriousness", term=ep.term, source="precedent",
                                  applied=False,
                                  note=f"過去症例の重篤度: {_fmt_counts(ep.seriousness)}")
                )
            if ep.n_cases and ep.causality:
                items.append(
                    InfluenceItem(axis="causality", term=ep.term, source="precedent",
                                  applied=False,
                                  note=f"過去症例の因果: {_fmt_counts(ep.causality)}")
                )
        return items
