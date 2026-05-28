import logging

from openai import OpenAI

from app.schemas import Chunk, EmbeddedChunk

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generate embeddings for chunks and queries using OpenAI API"""
    
    def __init__(self,
                 client: OpenAI, 
                 model: str = "text-embedding-3-small", 
                 batch_size:int = 100):
        self.client = client
        self.model = model
        self.batch_size = batch_size

    def embed_chunks(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        if not chunks:
            return []
        
        embedded_chunks = []

        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i:i+self.batch_size]

            texts = [chunk.text for chunk in batch]

            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )

            vectors = response.data

            for chunk, vector in zip(batch, vectors):
                embedded_chunk = EmbeddedChunk(chunk=chunk, embedding=vector.embedding)
                embedded_chunks.append(embedded_chunk)

        return embedded_chunks
    
    def embed_query(self, query:str) -> list[float]:
        response = self.client.embeddings.create(
            model=self.model,
            input=[query]
        )

        return response.data[0].embedding