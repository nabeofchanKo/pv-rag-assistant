import streamlit as st
import requests

API_BASE = "http://localhost:8000"


st.title("PV RAG Assistant")

st.header("Upload Document")
uploaded_file = st.file_uploader("Choose a PDF", type="pdf")
if uploaded_file is not None:
    if st.button("Upload"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
        response = requests.post(f"{API_BASE}/documents/upload", files=files)
        data = response.json()
        st.success(f"{data['message']} ({data['chunks_added']} chunks from {data['document_name']})")

st.header("Ask a Question")
query = st.text_input("Your question")
if st.button("Search"):
    if query:
        response = requests.post(
            f"{API_BASE}/query",
            json={"query": query, "top_k": 3},
        )
        data = response.json()
        answer = data["answer"]
        source = data["sources"]
        st.write(answer)
        with st.expander("Sources"):
            for src in data["sources"]:
                st.write(f"**{src['document_name']}** (page {src['page_number']})")
                st.write(src["text"])
                st.divider()

    else:
        st.warning("Please enter a question.")