"""Generate a context-grounded answer with a LangChain LCEL chain."""

import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.schemas import Chunk, RAGResponse

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "あなたは医薬品安全性監視（ファーマコビジランス, PV）を専門とするアシスタントです。"
    "回答は必ず、提供された『コンテキスト』の情報のみに基づいて作成してください。"
    "コンテキストに答えが含まれていない場合は、推測せず、"
    "「提供された資料には該当する情報が含まれていません。」と述べてください。"
    "外部知識や一般常識で補完してはいけません。"
    "可能な場合は、根拠とした出典番号（Source N）を回答中で示してください。"
    "原則として、ユーザーの質問と同じ言語で回答してください。"
)


class GeneratorService:
    """Generate an answer from retrieved chunks using an LCEL chain."""

    def __init__(self, llm: BaseChatModel) -> None:
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "Context:\n{context}\n\nQuestion: {question}"),
            ]
        )
        # LCEL: prompt -> chat model -> string. The pipe operator wires the steps.
        self.chain = self.prompt | self.llm | StrOutputParser()

    def _build_context(self, chunks: list[Chunk]) -> str:
        """Build a numbered context string from chunks."""

        context_parts = []
        for source_number, chunk in enumerate(chunks, start=1):
            context = (
                f"[Source {source_number}: {chunk.document_name}, "
                f"page {chunk.page_number}]\n{chunk.text}"
            )
            context_parts.append(context)

        return "\n\n".join(context_parts)

    def generate(self, query: str, chunks: list[Chunk]) -> RAGResponse:
        """Send the query with its context and generate a grounded answer."""

        context = self._build_context(chunks)
        answer = self.chain.invoke({"context": context, "question": query})

        return RAGResponse(answer=answer, source_chunks=chunks, query=query)
