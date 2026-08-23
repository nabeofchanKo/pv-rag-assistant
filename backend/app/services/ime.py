"""IME (Important Medical Events) reference — PT-keyed support for E2A criterion 6.

A drug-independent list of MedDRA PTs considered inherently medically important.
Because adverse events are already coded to a PT, criterion 6 can be flagged
deterministically when the coded PT is on this list — and the list is meant to be
**appended to via HITL** (a reviewer who assesses an event as criterion-6 serious
adds its PT; see `promote`). Missing file is non-fatal: criterion 6 then relies
only on the LLM.
"""

import csv
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


class ImeReference:
    """Membership test + HITL growth for the important-medical-events PT list.

    A single instance is shared (DI singleton) between the seriousness service and
    the review endpoint, so a `promote` from a review is visible to the very next
    assessment in the same process — no restart needed.
    """

    def __init__(self, csv_path: str) -> None:
        self.path = Path(csv_path)
        self._lock = threading.Lock()
        self.codes = self._load(self.path)

    def _load(self, path: Path) -> set[str]:
        if not path.exists():
            logger.warning("IME reference not found: %s (criterion 6 = LLM only)", path)
            return set()
        codes: set[str] = set()
        with path.open(encoding="utf-8") as f:
            rows = (line for line in f if not line.lstrip().startswith("#"))
            for row in csv.DictReader(rows):
                code = (row.get("pt_code") or "").strip()
                if code:
                    codes.add(code)
        logger.info("Loaded %d IME PTs from %s", len(codes), path)
        return codes

    def contains(self, pt_code: str | None) -> bool:
        return bool(pt_code) and pt_code in self.codes

    def promote(self, pt_code: str, pt_name: str, note: str = "") -> bool:
        """Add a PT to the IME list (HITL). Updates the in-memory set AND appends a
        row to the CSV so the growth persists. Idempotent: returns True if newly
        added, False if the PT was already present (no duplicate row written)."""
        pt_code = (pt_code or "").strip()
        if not pt_code:
            return False
        with self._lock:
            if pt_code in self.codes:
                return False
            self.codes.add(pt_code)
            self._append_row(pt_code, pt_name, note)
            logger.info("Promoted PT %s (%s) to IME list", pt_code, pt_name)
            return True

    def _append_row(self, pt_code: str, pt_name: str, note: str) -> None:
        new_file = not self.path.exists()
        if new_file:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if new_file:
                writer.writerow(["pt_code", "pt_name_ja", "note"])
            writer.writerow([pt_code, pt_name, note])
