"""OCR for image inputs.

The OCR engine is kept behind an interface so it can be swapped later (a Vision
LLM today; a local engine such as Tesseract/PaddleOCR as a privacy tier later),
mirroring how the embedding and chat models are injected.

Design principle: OCR performs *faithful transcription only* — no interpretation,
summarization, or translation. Interpretation/extraction is a later phase, which
keeps every downstream answer traceable to the transcribed source text.
"""

import base64
import logging
from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


OCR_PROMPT = (
    "あなたはOCRエンジンです。画像に写っている文字を、そのまま忠実に文字起こししてください。\n"
    "・書かれている内容のみを出力し、解釈・要約・補足・翻訳は一切行わないこと。\n"
    "・レイアウト上の改行はできる範囲で保持すること。\n"
    "・判読できない箇所は […] と表記すること。\n"
    "・前置きや説明（「以下が文字起こしです」等）は付けず、本文のみを出力すること。"
)


def _content_to_text(content: object) -> str:
    """Coerce a chat message's content (str or list of blocks) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


class OcrEngine(ABC):
    """Transcribe the text visible in an image."""

    @abstractmethod
    def transcribe(self, image_bytes: bytes, mime_type: str) -> str:
        ...


class VisionLLMOcrEngine(OcrEngine):
    """OCR via a vision-capable chat model (e.g. gpt-4o)."""

    def __init__(self, llm: BaseChatModel, prompt: str = OCR_PROMPT) -> None:
        self.llm = llm
        self.prompt = prompt

    def transcribe(self, image_bytes: bytes, mime_type: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        message = HumanMessage(
            content=[
                {"type": "text", "text": self.prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                },
            ]
        )
        result = self.llm.invoke([message])
        return _content_to_text(result.content)
