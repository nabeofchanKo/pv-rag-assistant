import requests
import streamlit as st

API_BASE = "http://localhost:8000"

SOURCE_LABELS = {"reported": "報告済み", "narrative": "経過から読取り"}
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "eml", "txt", "md"]

st.set_page_config(page_title="PV Triage Assistant", layout="wide")
st.title("PV Triage Assistant")

triage_tab, rag_tab = st.tabs(["🩺 症例トリアージ", "🔎 RAG Q&A"])


with triage_tab:
    st.caption(
        "有害事象報告（PDF / 画像スキャン / メール / テキスト）をアップロードすると、"
        "自社品判定と患者・有害事象の抽出案を返します。"
    )
    case_file = st.file_uploader("症例ファイルを選択", type=UPLOAD_TYPES, key="triage_upload")

    if case_file is not None and st.button("トリアージ実行", type="primary"):
        with st.spinner("解析中..."):
            files = {"file": (case_file.name, case_file.getvalue())}
            resp = requests.post(f"{API_BASE}/cases/triage", files=files)

        if resp.status_code != 200:
            st.error(f"エラー ({resp.status_code}): {resp.text}")
        else:
            data = resp.json()
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

            st.subheader("③ 有害事象")
            rows = [
                {
                    "事象": ae["term"],
                    "出典": SOURCE_LABELS.get(ae["source"], ae["source"]),
                    "発現日": ae.get("onset_date") or "—",
                    "転帰": ae.get("outcome") or "—",
                    "報告重篤度": ae.get("seriousness_reported") or "—",
                }
                for ae in ext["adverse_events"]
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)

            with st.expander("読み取ったテキスト（出典）"):
                st.text(data["source_text"])


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
