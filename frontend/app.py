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
CAUSAL_LABELS = {"否定できない": "🔴 否定できない", "否定できる": "🟢 否定できる", "評価不能": "⚪ 評価不能"}
UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "eml", "txt", "md"]

# Allowed verdicts per review axis (mirror of the backend ALLOWED_VERDICTS).
SER_OPTIONS = ["重篤", "非重篤", "要確認"]
CAU_OPTIONS = ["否定できない", "否定できる", "評価不能"]
EXP_OPTIONS = ["既知", "要確認", "未知", "判定不能"]
AXIS_LABELS = {"seriousness": "重篤度", "causality": "因果関係", "expectedness": "既知/未知"}


def _counts(d: dict | None) -> str:
    """Render a verdict->count dict as '重篤2／非重篤1' (or '—' when empty)."""
    if not d:
        return "—"
    return "／".join(f"{k}{v}" for k, v in d.items())


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


def post_triage(filename: str, content: bytes, influence: str = "applied"):
    with st.spinner("解析中..."):
        return requests.post(
            f"{API_BASE}/cases/triage",
            params={"influence": influence},
            files={"file": (filename, content)},
        )


def start_triage(filename: str, content: bytes, influence: str = "applied") -> None:
    """Start a triage run; stash the returned draft (awaiting review) in state."""
    resp = post_triage(filename, content, influence)
    if resp.status_code != 200:
        st.session_state.pop("case", None)
        st.error(f"エラー ({resp.status_code}): {resp.text}")
    else:
        st.session_state["case"] = resp.json()


def submit_decision(thread_id: str, decision: dict) -> None:
    with st.spinner("確定中..."):
        r = requests.post(f"{API_BASE}/cases/{thread_id}/approve", json=decision)
    if r.status_code != 200:
        st.error(f"エラー ({r.status_code}): {r.text}")
    else:
        st.session_state["case"] = r.json()
        st.rerun()


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

    st.subheader("⑥ 因果関係（時間的・保守的評価）")
    causality = data.get("causality") or []
    if causality:
        st.caption(
            "トリアージの保守的評価：本剤投与後に発現＝🔴 否定できない（スコープ維持）。"
            "投与開始前、または中止後で明らかに時間的に不整合な時のみ 🟢 否定できる。"
        )
    cau_rows = [
        {
            "事象": c["term"],
            "因果関係": CAUSAL_LABELS.get(c["verdict"], c["verdict"]),
            "発現時期": c.get("onset_relation") or "—",
            "根拠": c.get("evidence_quote") or (c.get("rationale") or "—"),
        }
        for c in causality
    ]
    if cau_rows:
        st.dataframe(cau_rows, use_container_width=True, hide_index=True)

    st.subheader("⑦ 過去症例の判例（一貫性）")
    precedent = [p for p in (data.get("precedent") or []) if p.get("n_cases")]
    if not precedent:
        st.info("同一MedDRA PTの過去承認症例は見つかりませんでした。")
    else:
        st.caption(
            "過去に承認された症例で同じMedDRA PTがどう判定されたか（参考情報・自動では判定を変えません）。"
            "⚠️ は今回のドラフトと過去の多数派が不一致で、レビュー要注意です。"
        )
        prec_rows = []
        for p in precedent:
            conflict_axes = "・".join(AXIS_LABELS.get(a, a) for a in p.get("conflicts") or [])
            prec_rows.append(
                {
                    "事象": p["term"],
                    "過去件数": p["n_cases"],
                    "重篤度(過去)": _counts(p.get("seriousness")),
                    "因果(過去)": _counts(p.get("causality")),
                    "既知/未知(過去)": _counts(p.get("expectedness")),
                    "不一致": f"⚠️ {conflict_axes}" if conflict_axes else "",
                    "参照症例": "、".join(p.get("case_ids") or []),
                }
            )
        st.dataframe(prec_rows, use_container_width=True, hide_index=True)

    mode = data.get("influence_mode", "applied")
    influence = data.get("influence") or []
    SRC = {"IME": "以前のFB(IME)", "precedent": "過去症例"}
    if mode == "applied":
        st.markdown(f"**過去データの反映**（モード: 🟢 反映）")
        applied_items = [i for i in influence if i.get("applied")]
        if applied_items:
            st.caption("過去データにより、以下を安全側に調整しました（監査対象）。")
            st.dataframe(
                [
                    {
                        "事象": i["term"],
                        "軸": AXIS_LABELS.get(i["axis"], i["axis"]),
                        "由来": SRC.get(i["source"], i["source"]),
                        "変更": f'{i.get("from_verdict")}→{i.get("to_verdict")}',
                        "内容": i["note"],
                    }
                    for i in applied_items
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("今回、過去データによる調整はありませんでした。")
    else:
        st.markdown(f"**過去データ（参考）**（モード: ⚪ 参考・判定は今回の症例のみ）")
        if influence:
            st.caption("以下は参考情報です。今回の判定には反映していません。")
            st.dataframe(
                [
                    {
                        "事象": i["term"],
                        "軸": AXIS_LABELS.get(i["axis"], i["axis"]),
                        "由来": SRC.get(i["source"], i["source"]),
                        "メモ": i["note"],
                    }
                    for i in influence
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("参考にできる過去データはありませんでした。")

    with st.expander("読み取ったテキスト（出典）"):
        st.text(data["source_text"])


def _override_editor(axis: str, items: list, options: list, key: str) -> list:
    """One editable table for a per-AE axis; return the rows the reviewer changed."""
    if not items:
        return []
    st.caption(AXIS_LABELS[axis])
    rows = [{"事象": x["term"], "現在": x["verdict"], "変更後": x["verdict"], "理由": ""} for x in items]
    edited = st.data_editor(
        rows,
        key=key,
        hide_index=True,
        use_container_width=True,
        column_config={
            "変更後": st.column_config.SelectboxColumn("変更後", options=options, required=True),
            "理由": st.column_config.TextColumn("変更理由"),
        },
        disabled=["事象", "現在"],
    )
    out = []
    for r in edited:
        if r["変更後"] != r["現在"]:
            out.append(
                {"axis": axis, "term": r["事象"], "new_verdict": r["変更後"],
                 "rationale": r["理由"] or None}
            )
    return out


def _expectedness_override_editor(drugs: list, key: str) -> list:
    out = []
    for di, drug in enumerate(drugs):
        items = drug.get("assessments") or []
        if not items:
            continue
        st.caption(f"{AXIS_LABELS['expectedness']}（{drug['drug_name']}）")
        rows = [{"事象": a["term"], "現在": a["verdict"], "変更後": a["verdict"], "理由": ""} for a in items]
        edited = st.data_editor(
            rows,
            key=f"{key}_{di}",
            hide_index=True,
            use_container_width=True,
            column_config={
                "変更後": st.column_config.SelectboxColumn("変更後", options=EXP_OPTIONS, required=True),
                "理由": st.column_config.TextColumn("変更理由"),
            },
            disabled=["事象", "現在"],
        )
        for r in edited:
            if r["変更後"] != r["現在"]:
                out.append(
                    {"axis": "expectedness", "term": r["事象"], "drug_name": drug["drug_name"],
                     "new_verdict": r["変更後"], "rationale": r["理由"] or None}
                )
    return out


def _ime_promotion_editor(case: dict, key: str) -> list:
    """Checkbox table over events with a coded PT; return the PTs to promote."""
    seen, rows = set(), []
    for m in case.get("meddra") or []:
        code = m.get("pt_code")
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append(
            {"事象": m["term"], "PT名": m.get("pt_name_ja") or "—", "PTコード": code,
             "IMEに追加": False, "理由": ""}
        )
    if not rows:
        return []
    st.markdown(
        "**IMEリストへの昇格（任意）** — 「医学的に重要」と判断したPTを追加すると、"
        "今後の症例で同じPTの事象が自動的に重篤（criterion 6）になります。"
    )
    edited = st.data_editor(
        rows,
        key=key,
        hide_index=True,
        use_container_width=True,
        column_config={
            "IMEに追加": st.column_config.CheckboxColumn("IMEに追加", default=False),
            "理由": st.column_config.TextColumn("昇格理由"),
        },
        disabled=["事象", "PT名", "PTコード"],
    )
    return [
        {"pt_code": r["PTコード"], "pt_name": r["PT名"], "rationale": r["理由"] or None}
        for r in edited
        if r["IMEに追加"]
    ]


def _extraction_editor(case: dict, key: str):
    """Editable table over extracted events: remove (checkbox) + fix MedDRA PT.
    Returns (removed_terms, recoded)."""
    aes = case["extraction"]["adverse_events"]
    med = {m["term"]: m for m in (case.get("meddra") or [])}
    rows = [
        {
            "事象": ae["term"],
            "削除": False,
            "PTコード": (med.get(ae["term"], {}).get("pt_code") or ""),
            "PT名": (med.get(ae["term"], {}).get("pt_name_ja") or ""),
        }
        for ae in aes
    ]
    if not rows:
        return [], []
    st.caption("誤抽出は「削除」にチェック。MedDRAが違う場合は PTコード / PT名 を直接修正。")
    edited = st.data_editor(
        rows, key=key, hide_index=True, use_container_width=True,
        column_config={
            "削除": st.column_config.CheckboxColumn("削除", default=False),
            "PTコード": st.column_config.TextColumn("PTコード"),
            "PT名": st.column_config.TextColumn("PT名"),
        },
        disabled=["事象"],
    )
    removed, recoded = [], []
    for r, orig in zip(edited, rows):
        if r["削除"]:
            removed.append(r["事象"])
            continue
        if (r["PTコード"] or "") != (orig["PTコード"] or "") and (r["PTコード"] or "").strip():
            recoded.append({"term": r["事象"], "pt_code": r["PTコード"].strip(),
                            "pt_name": (r["PT名"] or r["PTコード"]).strip()})
    return removed, recoded


def _add_event_editor(key: str):
    """Dynamic table to add missed events with manual verdicts. Returns added_events."""
    st.caption("見落とし事象を追加（判定は手入力。行を足せます）。")
    template = [{"事象": "", "PTコード": "", "PT名": "", "重篤度": "要確認", "因果": "否定できない"}]
    edited = st.data_editor(
        template, key=key, num_rows="dynamic", hide_index=True, use_container_width=True,
        column_config={
            "重篤度": st.column_config.SelectboxColumn("重篤度", options=SER_OPTIONS, required=True),
            "因果": st.column_config.SelectboxColumn("因果", options=CAU_OPTIONS, required=True),
        },
    )
    added = []
    for r in edited:
        term = (r.get("事象") or "").strip()
        if not term:
            continue
        added.append({
            "term": term,
            "pt_code": (r.get("PTコード") or "").strip() or None,
            "pt_name": (r.get("PT名") or "").strip() or None,
            "seriousness": r.get("重篤度") or "要確認",
            "causality": r.get("因果") or "否定できない",
        })
    return added


def render_review(case: dict) -> None:
    """The Phase 4b HITL gate: review the draft, override verdicts, approve/reject."""
    st.divider()
    st.subheader("⑧ レビュー・承認（HITL）")
    status = case.get("status")

    if status in ("approved", "rejected"):
        review = case.get("review") or {}
        who, when = review.get("reviewer", "—"), review.get("reviewed_at", "")
        if status == "approved":
            st.success(f"✅ 承認済み — 担当: {who} / {when}")
        else:
            st.error(f"⛔ 却下 — 担当: {who} / {when}")
        if review.get("note"):
            st.caption(f"所見: {review['note']}")
        overrides = review.get("overrides") or []
        if overrides:
            st.markdown("**人手による上書き（監査証跡）**")
            st.dataframe(
                [
                    {
                        "軸": AXIS_LABELS.get(o["axis"], o["axis"]),
                        "事象": o["term"],
                        "製品": o.get("drug_name") or "—",
                        "元の判定": o["original_verdict"],
                        "変更後": o["new_verdict"],
                        "理由": o.get("rationale") or "—",
                    }
                    for o in overrides
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("上書きなし（ドラフトのまま承認）。")
        edits = review.get("extraction_edits") or []
        if edits:
            st.markdown("**抽出の修正（監査証跡）**")
            KIND = {"removed": "削除", "added": "追加", "recoded": "PT修正"}
            st.dataframe(
                [{"種別": KIND.get(e["kind"], e["kind"]), "事象": e["term"], "詳細": e.get("detail") or "—"}
                 for e in edits],
                use_container_width=True, hide_index=True,
            )
        promotions = review.get("ime_promotions") or []
        if promotions:
            st.markdown("**IMEリストへ昇格したPT（今後の症例に反映）**")
            st.dataframe(
                [
                    {
                        "PT名": p["pt_name"],
                        "PTコード": p["pt_code"],
                        "状態": p["status"],
                        "理由": p.get("rationale") or "—",
                    }
                    for p in promotions
                ],
                use_container_width=True,
                hide_index=True,
            )
        if st.button("別の症例をレビューする"):
            st.session_state.pop("case", None)
            st.rerun()
        return

    # awaiting_review
    escalations = case.get("escalations") or []
    if escalations:
        st.warning("安全側で『要確認 / 評価不能』の項目があります。判断のうえ承認してください。")
        st.dataframe(
            [
                {
                    "軸": AXIS_LABELS.get(e["axis"], e["axis"]),
                    "事象": e["term"],
                    "製品": e.get("drug_name") or "—",
                    "判定": e["verdict"],
                    "理由": e["reason"],
                }
                for e in escalations
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("安全側の要確認項目はありません。内容を確認して承認してください。")

    reviewer = st.text_input("レビュー担当者名（必須）", key="reviewer")
    note = st.text_area("全体所見（任意）", key="review_note")

    st.markdown("**判定の上書き（任意）** — 「変更後」を変えるとその項目が上書きされます。")
    overrides = []
    overrides += _override_editor("seriousness", case.get("seriousness") or [], SER_OPTIONS, "ov_ser")
    overrides += _override_editor("causality", case.get("causality") or [], CAU_OPTIONS, "ov_cau")
    overrides += _expectedness_override_editor(case.get("expectedness") or [], "ov_exp")

    promotions = _ime_promotion_editor(case, "ov_ime")

    st.markdown("**抽出の修正（任意）** — 削除・MedDRA修正・見落とし追加。")
    removed_terms, recoded = _extraction_editor(case, "edit_extract")
    added_events = _add_event_editor("edit_add")

    thread_id = case["thread_id"]
    edits = {"removed_terms": removed_terms, "added_events": added_events, "recoded": recoded}
    col1, col2 = st.columns(2)
    if col1.button("承認する", type="primary"):
        if not reviewer:
            st.error("レビュー担当者名は必須です。")
        else:
            submit_decision(
                thread_id,
                {"action": "approve", "reviewer": reviewer, "note": note or None,
                 "overrides": overrides, "ime_promotions": promotions, **edits},
            )
    if col2.button("却下する"):
        if not reviewer:
            st.error("レビュー担当者名は必須です。")
        else:
            submit_decision(
                thread_id,
                {"action": "reject", "reviewer": reviewer, "note": note or None,
                 "overrides": [], "ime_promotions": []},
            )


with triage_tab:
    st.caption(
        "有害事象報告（PDF / 画像スキャン / メール / テキスト）をアップロードすると、"
        "6項目のトリアージ案を生成し、人手レビュー（承認/修正）に回します。"
    )

    mode_label = st.radio(
        "過去データ（過去症例・以前のFB）の扱い",
        ["反映（判定に織り込む）", "参考（メモのみ・今回の症例だけで判定）"],
        horizontal=True,
        key="influence_mode",
        help="反映：IME昇格→重篤（確定）、過去症例→安全側で要確認に引き上げ。参考：判定は変えず過去はメモ表示。",
    )
    influence = "advisory" if mode_label.startswith("参考") else "applied"

    case_file = st.file_uploader("症例ファイルを選択", type=UPLOAD_TYPES, key="triage_upload")
    if case_file is not None and st.button("トリアージ実行", type="primary"):
        start_triage(case_file.name, case_file.getvalue(), influence)

    st.markdown("**同梱サンプルで試す**（アップロード不要）")
    samples = sorted(
        p.name for p in SAMPLE_DIR.glob("*") if p.suffix.lower().lstrip(".") in UPLOAD_TYPES
    )
    if samples:
        sample = st.selectbox("サンプル症例", samples, key="triage_sample")
        if st.button("サンプルでトリアージ", key="triage_sample_btn"):
            start_triage(sample, (SAMPLE_DIR / sample).read_bytes(), influence)

    if "case" in st.session_state:
        st.divider()
        render_triage(st.session_state["case"])
        render_review(st.session_state["case"])


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
