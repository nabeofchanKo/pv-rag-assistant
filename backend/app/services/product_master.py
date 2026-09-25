"""Own-company product matching (自社品判定).

Deterministic alias matching against a YAML product master: a case is in
evaluation scope if any master product's name / active ingredient / alias appears
in the (NFKC-normalized) case text. Deterministic on purpose — the match is
auditable ("matched because this alias appears") and costs nothing. The heavy
lifting for reporter wording variability lives in each product's `aliases`.
"""

import logging
import unicodedata
from pathlib import Path

import yaml

from app.schemas import ProductMatch, ProductMatchResult

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


class ProductMasterService:
    """Match own-company products from a YAML master against case text."""

    def __init__(self, master_path: str) -> None:
        self.products = self._load(Path(master_path))

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            raise FileNotFoundError(f"Product master not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        products = data.get("products", [])
        logger.info("Loaded %d products from %s", len(products), path)
        return products

    def match(self, text: str) -> ProductMatchResult:
        normalized = _normalize(text)
        matches: list[ProductMatch] = []

        for product in self.products:
            candidates = [product["name"]]
            if product.get("active_ingredient"):
                candidates.append(product["active_ingredient"])
            candidates.extend(product.get("aliases", []))

            hit = next((c for c in candidates if _normalize(c) in normalized), None)
            if hit is not None:
                matches.append(
                    ProductMatch(
                        name=product["name"],
                        matched_via=hit,
                        active_ingredient=product.get("active_ingredient"),
                        notes=(product.get("notes") or "").strip() or None,
                        label_document=product.get("label_document"),
                    )
                )

        return ProductMatchResult(matched_products=matches)
