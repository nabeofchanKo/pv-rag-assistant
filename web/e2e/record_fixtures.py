"""Record the fixtures the E2E suite replays.

The Playwright suite runs the real browser and the real Next.js BFF against a
*fake* backend (e2e/fake-backend.mjs) so it is free, deterministic and safe to
run anywhere. The fake only replays JSON — so that JSON has to be what the real
backend actually returns, or the suite would be testing the UI against a shape
nobody produces. This script is where that JSON comes from: it drives the real
FastAPI app in-process (real LLM calls, a few cents) and writes the responses.

Re-run it whenever the backend response shape changes; the contract test
(backend/tests/test_frontend_contract.py) is what tells you that happened.

Isolation — approving a case in the real app mutates tracked data (IME list,
precedent store, checkpoints). Every one of those paths is pointed at a temp
dir BEFORE the app is imported, so recording leaves `git status` clean.

Run from the repo root:
    TIKTOKEN_CACHE_DIR=backend/.tiktoken_cache \
        venv/Scripts/python.exe web/e2e/record_fixtures.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SAMPLES = REPO / "web" / "public" / "samples"
OUT = Path(__file__).resolve().parent / "fixtures"

# ---- isolate every write path before app.config is imported ----
tmp = Path(tempfile.mkdtemp(prefix="e2e-record-"))
shutil.copy(REPO / "data" / "reference" / "ime_pt.csv", tmp / "ime_pt.csv")
os.environ["IME_PATH"] = str(tmp / "ime_pt.csv")
os.environ["PAST_CASES_RUNTIME_DIR"] = str(tmp / "past_cases")
os.environ["CHECKPOINT_DB_PATH"] = str(tmp / "triage.sqlite")
os.environ.pop("INTERNAL_API_TOKEN", None)  # in-process: no BFF secret needed

sys.path.insert(0, str(REPO / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# The first seriousness verdict is overridden to a different value, so the
# recorded approval exercises the audit trail (original → new) — the part of
# the review flow a regression would most plausibly break.
SER_CYCLE = {"非重篤": "要確認", "要確認": "重篤", "重篤": "要確認"}


def triage(client: TestClient, sample: str) -> dict:
    with open(SAMPLES / sample, "rb") as f:
        r = client.post("/cases/triage", files={"file": (sample, f, "text/plain")})
    r.raise_for_status()
    return r.json()


def write(name: str, data: dict) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(REPO)}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    with TestClient(app) as client:  # `with` runs the lifespan (reference indexing)
        print("case_001 → draft")
        draft = triage(client, "case_001.txt")
        assert draft["status"] == "awaiting_review", draft["status"]
        write("case_001.draft.json", draft)

        target = draft["seriousness"][0]
        decision = {
            "action": "approve",
            "reviewer": "E2Eテスト担当",
            "note": "E2E 録画用の承認",
            "overrides": [
                {
                    "axis": "seriousness",
                    "term": target["term"],
                    "new_verdict": SER_CYCLE[target["verdict"]],
                    "rationale": "E2E: 上書きの監査証跡を確認",
                }
            ],
            "ime_promotions": [],
            "removed_terms": [],
            "added_events": [],
            "recoded": [],
        }
        print("case_001 → approve (1 override)")
        r = client.post(f"/cases/{draft['thread_id']}/approve", json=decision)
        r.raise_for_status()
        write("case_001.approve.request.json", decision)
        write("case_001.approved.json", r.json())

        print("case_004 → out_of_scope")
        oos = triage(client, "case_004.txt")
        assert oos["status"] == "out_of_scope", oos["status"]
        write("case_004.out_of_scope.json", oos)

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
