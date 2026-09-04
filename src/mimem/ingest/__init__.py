"""Ingestion adapters. Importing this package registers every built-in adapter."""

from mimem.ingest import epub as _epub  # noqa: F401  (registers EpubAdapter)
from mimem.ingest import pdf as _pdf  # noqa: F401  (registers PdfAdapter)
from mimem.ingest import text as _text  # noqa: F401  (registers TextAdapter)
from mimem.ingest.base import Adapter, IngestError, adapter_for, available_extensions, load

__all__ = ["Adapter", "IngestError", "adapter_for", "available_extensions", "load"]
