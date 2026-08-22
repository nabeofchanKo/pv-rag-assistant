"""IME (Important Medical Events) reference — PT-keyed support for E2A criterion 6.

A drug-independent list of MedDRA PTs considered inherently medically important.
Because adverse events are already coded to a PT, criterion 6 can be flagged
deterministically when the coded PT is on this list — and the list is meant to be
**appended to via HITL** (a reviewer who assesses an event as criterion-6 serious
adds its PT). Missing file is non-fatal: criterion 6 then relies only on the LLM.
"""

import csv
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ImeReference:
    """Membership test: is this MedDRA PT on the important-medical-events list?"""

    def __init__(self, csv_path: str) -> None:
        self.codes = self._load(Path(csv_path))

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
