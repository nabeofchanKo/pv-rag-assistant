"""Unit tests for ProductMasterService, focused on the label_document link
that expectedness relies on to find the right drug's package insert."""

import textwrap

from app.services.product_master import ProductMasterService


def _write_master(tmp_path):
    path = tmp_path / "products.yaml"
    path.write_text(
        textwrap.dedent(
            """
            products:
              - name: DrugX
                active_ingredient: Compound-X
                aliases: [ドラッグX]
                label_document: drugx_label.md
              - name: DrugQ
                active_ingredient: Compound-Q
                aliases: [ドラッグQ]
            """
        ),
        encoding="utf-8",
    )
    return str(path)


def test_match_exposes_label_document(tmp_path):
    svc = ProductMasterService(_write_master(tmp_path))
    result = svc.match("患者にドラッグXを投与した。")

    assert result.is_company_product_present
    match = result.matched_products[0]
    assert match.name == "DrugX"
    assert match.label_document == "drugx_label.md"


def test_label_document_is_none_when_absent(tmp_path):
    svc = ProductMasterService(_write_master(tmp_path))
    result = svc.match("患者にドラッグQを投与した。")

    assert result.matched_products[0].label_document is None
