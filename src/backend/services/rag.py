"""Stable public imports for the Gemini-only RAG implementation."""

from src.backend.services.rag_core import (
    RAGService,
    get_rag_service,
    text_has_price_evidence,
)

__all__ = ["RAGService", "get_rag_service", "text_has_price_evidence"]
