"""Conservative temporal causality check (evidence for ADR 0005).

Runs the live CausalityService over case_003 and prints the temporal relation +
verdict per event, to confirm during-treatment events stay 否定できない and that
post-discontinuation onsets respect residual/delayed effects.

Run from the repo root (needs backend/.env with OPENAI_API_KEY):
    PYTHONPATH=backend python experiments/scripts/causality_temporal.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.dependencies import get_causality_service  # noqa: E402
from app.schemas import AdverseEventMention  # noqa: E402

# case_003 adverse events with onset dates (DrugZ start 2025-09-10).
AES = [
    ("INR増加", "2025-10-12"), ("鼻出血", "2025-10-14"), ("斑状出血", "2025-10-15"),
    ("徐脈", "2025-11-22"), ("失神", "2025-11-22"), ("起立性低血圧", "2025-11-23"),
    ("錯乱状態", "2025-12-15"), ("浮動性めまい", "2025-12-15"),
]

svc = get_causality_service()
text = (ROOT / "data" / "sample_reports" / "case_003.txt").read_text(encoding="utf-8")
mentions = [AdverseEventMention(term=t, source="reported", onset_date=o) for t, o in AES]

print(f"{'event':<14} | {'onset_relation':<10} | verdict")
print("-" * 48)
for c in svc.assess(text, mentions, ["DrugZ"]):
    print(f"{c.term:<14} | {(c.onset_relation or '-'):<10} | {c.verdict}")
