"""
Builds or loads a persistent Chroma vector store over the knowledge base.
Swap the embedding model here if you ever move off Gemini — nothing else
in crag/ needs to change.
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from .ingest import chunk_documents, load_documents

EMBEDDING_MODEL = "gemini-embedding-001"

# This index must be rebuilt after changing embedding models.
# name this used to be) is deprecated and now returns a hard 404 as of
# Feb 2026 — confirmed via Google's own docs and multiple developer
# reports. This is the current GA replacement.
#
# IMPORTANT: switching embedding models isn't just a constant swap — old
# vectors in .crag_index were computed with the OLD model and aren't
# comparable to new ones (different model = different vector space
# entirely). Delete the .crag_index folder (or pass force_rebuild=True to
# CragEngine once) after this change, or you'll be silently searching
# against a broken/mismatched index.


def build_vector_store(knowledge_dir: str, persist_dir: str, force_rebuild: bool = False) -> Chroma:
    embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    persist_path = Path(persist_dir)

    if persist_path.exists() and not force_rebuild:
        return Chroma(persist_directory=str(persist_path), embedding_function=embeddings)

    docs = load_documents(knowledge_dir)
    chunks = chunk_documents(docs)
    store = Chroma.from_documents(chunks, embeddings, persist_directory=str(persist_path))
    return store
