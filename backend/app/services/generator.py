import logging

from openai import OpenAI

from app.schemas import Chunk, RAGResponse

logger = logging.getLogger(__name__)


class GeneratorService:
    """Generate an answer with using OpenAI API."""

    def __init__(self, client: OpenAI, model: str = "gpt-4o-mini") -> None:
        self.client = client
        self.model = model

    def _build_context(self, chunks: list[Chunk]) -> str:
        """Build a context from chunks."""

        context_parts = []
        for source_number, chunk in enumerate(chunks, start=1):
            context = f"[Source {source_number}: {chunk.document_name}, page {chunk.page_number}]\n{chunk.text}"
            context_parts.append(context)

        return "\n\n".join(context_parts)
    
    def generate(self, query: str, chunks: list[Chunk]) -> RAGResponse:
        """Send a query and generate an answer from chunks."""
        
        context = self._build_context(chunks)

        system_prompt = (
            "You are a pharmacovigilance (PV) assistant specialized in adverse event reports. "
            "Answer the question based ONLY on the provided context. "
            "If the answer is not in the context, say \"The provided context does not contain this information.\" "
            "Do not speculate or use external knowledge. "
            "When possible, refer to the source numbers in your answer."
        )

        user_prompt = f"Context:\n{context}\n\nQuestion: {query}"

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )

        answer = response.choices[0].message.content or ""
        
        return RAGResponse(answer=answer, source_chunks=chunks, query=query)