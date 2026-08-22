from pathlib import Path

import requests
import streamlit as st

API_BASE = "http://localhost:8000"
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_reports"

SOURCE_LABELS = {"reported": "報告済み", "narrative": "経過から読取り"}
VERDICT_LABELS = {
    "既知": "🟢 既知",
    "要確認": "🟡 要確認（未知扱い）",
    "未知": "🔴 未知",
    "判定不能": "⚪ 判定不能",
}
SERIOUS_LABELS = {"重篤": "🔴 重篤", "要確認": "🟡 要確認", "非重篤": "⚪ 非重篤"}
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "eml", "txt", "md"]


def _reported_is_serious(reported):
    """Coarse serious/non from the transcribed reporter value (非重篤 contains 重篤)."""
    if not reported:
        return None
    if "非重篤" in reported:
        return False
    if "重篤" in reported:
        return True
    return None

st.set_page_config(page_title="PV Triage Assistant", layout="wide")
st.title("PV Triage Assistant")

triage_tab, rag_tab = st.tabs(["🩺 症例トリアージ", "🔎 RAG Q&A"])


def post_triage(filename: str, content: bytes):
    with st.spinner("解析中..."):
        return requests.post(f"{API_BASE}/cases/triage", files={"file": (filename, content)})


def render_triage(data: dict) -> None:
    pm = data["product_match"]
    st.subheader("① 自社品判定")
    if pm["is_company_product_present"]:
        names = "、".join(p["name"] for p in pm["matched_products"])
        st.success(f"自社品該当あり（評価対象）：{names}")
        for p in pm["matched_products"]:
            st.markdown(f"**{p['name']}**（ヒット語: `{p['matched_via']}`）")
            if p.get("notes"):
                st.caption(p["notes"])
    else:
        st.warning("自社品該当なし（評価対象外の可能性）")

    ext = data["extraction"]
    patient = ext["patient"]
    st.subheader("② 患者")
    col1, col2 = st.columns(2)
    col1.metric("年齢", patient.get("age") or "—")
    col2.metric("性別", patient.get("sex") or "—")

    st.subheader("③ 有害事象 ＋ MedDRAコード提案")
    meddra = data.get("meddra") or []
    rows = []
    for i, ae in enumerate(ext["adverse_events"]):
        m = meddra[i] if i < len(meddra) else {}
        rows.append(
            {
                "事象": ae["term"],
                "MedDRA PT": m.get("pt_name_ja") or "—",
                "PTコード": m.get("pt_code") or "—",
                "コード由来": m.get("coded_by") or "—",
                "出典": SOURCE_LABELS.get(ae["source"], ae["source"]),
                "発現日": ae.get("onset_date") or "—",
                "転帰": ae.get("outcome") or "—",
                "報告重篤度": ae.get("seriousness_reported") or "—",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.subheader("④ 重篤度（報告 vs 企業評価 / ICH E2A）")
    seriousness = data.get("seriousness") or []
    if seriousness:
        st.caption(
            "🔴 重篤 は基準1つ以上に該当、🟡 要確認 は疑いのみ（安全側でHITL）。"
            "『⚠️ 差異』は報告上の重篤度と企業評価がずれた事象（過小報告を防ぐ着目点）。"
        )
    ser_rows = []
    for s in seriousness:
        rep = s.get("reported")
        diff = _reported_is_serious(rep)
        flag = "⚠️ 差異" if (diff is not None and diff != s.get("is_serious")) else ""
        hits = s.get("hits") or []
        ser_rows.append(
            {
                "事象": s["term"],
                "報告重篤度": rep or "—",
                "企業評価": SERIOUS_LABELS.get(s["verdict"], s["verdict"]),
                "差異": flag,
                "該当基準": "、".join(h["criterion"] for h in hits) or "—",
                "根拠": next((h.get("evidence_quote") for h in hits if h.get("evidence_quote")), None)
                or (s.get("rationale") or "—"),
            }
        )
    if ser_rows:
        st.dataframe(ser_rows, use_container_width=True, hide_index=True)

    st.subheader("⑤ 既知/未知（添付文書との照合）")
    expectedness = data.get("expectedness") or []
    if not expectedness:
        st.info("該当する添付文書がないため、既知/未知は判定していません。")
    else:
        st.caption(
            "🟡 要確認 は、読み替え・機序の言及など一致が確実でないもの。安全側で未知として扱い、"
            "根拠を添えて人手確認（HITL）に回します（過度に既知と読み込んで報告漏れを招かないため）。"
        )
    for drug in expectedness:
        st.markdown(f"**{drug['drug_name']}**（添付文書: `{drug['label_document']}`）")
        exp_rows = [
            {
                "事象": a["term"],
                "判定": VERDICT_LABELS.get(a["verdict"], a["verdict"]),
                "一致": a.get("match_type") or "—",
                "該当箇所": a.get("evidence_section") or "—",
                "根拠（添付文書の記載）": a.get("evidence_quote") or (a.get("rationale") or "—"),
            }
            for a in drug["assessments"]
        ]
        st.dataframe(exp_rows, use_container_width=True, hide_index=True)

    with st.expander("読み取ったテキスト（出典）"):
        st.text(data["source_text"])


with triage_tab:
    st.caption(
        "有害事象報告（PDF / 画像スキャン / メール / テキスト）をアップロードすると、"
        "自社品判定と患者・有害事象の抽出案を返します。"
    )

    case_file = st.file_uploader("症例ファイルを選択", type=UPLOAD_TYPES, key="triage_upload")
    if case_file is not None and st.button("トリアージ実行", type="primary"):
        resp = post_triage(case_file.name, case_file.getvalue())
        if resp.status_code != 200:
            st.error(f"エラー ({resp.status_code}): {resp.text}")
        else:
            render_triage(resp.json())

    st.divider()
    st.markdown("**同梱サンプルで試す**（アップロード不要）")
    samples = sorted(
        p.name for p in SAMPLE_DIR.glob("*") if p.suffix.lower().lstrip(".") in UPLOAD_TYPES
    )
    if samples:
        sample = st.selectbox("サンプル症例", samples, key="triage_sample")
        if st.button("サンプルでトリアージ", key="triage_sample_btn"):
            resp = post_triage(sample, (SAMPLE_DIR / sample).read_bytes())
            if resp.status_code != 200:
                st.error(f"エラー ({resp.status_code}): {resp.text}")
            else:
                render_triage(resp.json())


with rag_tab:
    st.caption("文書をインデックスして、根拠付きで質問できます。")
    uploaded_file = st.file_uploader("文書を選択（PDF）", type="pdf", key="rag_upload")
    if uploaded_file is not None and st.button("アップロード＆インデックス"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
        response = requests.post(f"{API_BASE}/documents/upload", files=files)
        data = response.json()
        st.success(f"{data['message']} ({data['chunks_added']} chunks / {data['document_name']})")

    question = st.text_input("質問を入力")
    if st.button("検索"):
        if question:
            response = requests.post(
                f"{API_BASE}/query",
                json={"query": question, "top_k": 3},
            )
            data = response.json()
            st.write(data["answer"])
            with st.expander("出典"):
                for src in data["sources"]:
                    st.write(f"**{src['document_name']}** (page {src['page_number']})")
                    st.write(src["text"])
                    st.divider()
        else:
            st.warning("質問を入力してください。")
