"""How far can a reported term differ from the label wording and still be judged
既知? Evidence for ADR 0002 (the confidence gate). Runs DrugX against a spread of
near/loose synonyms through the live ExpectednessService and prints the verdict,
match_type, and cited evidence per term.

Run from the repo root (needs backend/.env with OPENAI_API_KEY):
    PYTHONPATH=backend python experiments/scripts/expectedness_synonym_tolerance.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.dependencies import get_expectedness_service, get_label_index_service  # noqa: E402

get_label_index_service().ensure_indexed()
svc = get_expectedness_service()

TERMS = ["めまい", "回転性めまい", "顔のほてり感", "疲れ", "浮腫", "だるさ", "血圧低下"]

result = svc.assess("DrugX", "drugx_label.md", TERMS)
print(f"{'AE語':<10} | {'判定':<6} | {'一致種類':<12} | 根拠(該当箇所)")
print("-" * 80)
for a in result.assessments:
    sec = a.evidence_section or "-"
    print(f"{a.term:<10} | {a.verdict:<6} | {(a.match_type or '-'):<12} | {sec}")
