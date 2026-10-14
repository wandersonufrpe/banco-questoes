"""Importa o PyMuPDF pelo nome novo (pymupdf) ou pelo antigo (fitz)."""

try:
    import pymupdf  # noqa: F401
except ImportError:  # PyMuPDF < 1.24
    import fitz as pymupdf  # noqa: F401
