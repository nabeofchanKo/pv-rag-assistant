"""Seriousness criterion attribution check (evidence for ADR 0004).

Runs the live SeriousnessService over two sample cases and prints reporter-vs-
company seriousness + matched criteria, to check that the hospitalization
criterion is attributed to the right event (not borrowed) and that severity is
not confused with seriousness.

Run from the repo root (needs backend/.env with OPENAI_API_KEY):
    PYTHONPATH=backend python experiments/scripts/seriousness_attribution.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.dependencies import get_seriousness_service  # noqa: E402
from app.schemas import AdverseEventMention  # noqa: E402

CASES = {
    "case_001": [("頭痛", "非重篤"), ("浮動性めまい", "非重篤"), ("悪心", "非重篤")],
    "case_003": [
        ("INR増加", "非重篤"), ("鼻出血", "非重篤"), ("斑状出血", "非重篤"),
        ("徐脈", "重篤"), ("失神", "重篤"), ("起立性低血圧", "非重篤"),
        ("錯乱状態", "非重篤"), ("浮動性めまい", "非重篤"),
    ],
}

svc = get_seriousness_service()
for name, aes in CASES.items():
    text = (ROOT / "data" / "sample_reports" / f"{name}.txt").read_text(encoding="utf-8")
    mentions = [
        AdverseEventMention(term=t, source="reported", seriousness_reported=r)
        for t, r in aes
    ]
    print(f"== {name} ==")
    for s in svc.assess(text, mentions, None):
        crit = "、".join(h.criterion for h in s.hits) or "-"
        print(f"  {s.term}: reported={s.reported} / assessed={s.verdict} [{crit}]")
