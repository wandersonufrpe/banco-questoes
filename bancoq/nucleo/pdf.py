"""PyMuPDF: importação e conversão de páginas de PDF em imagens."""

from __future__ import annotations

from pathlib import Path

try:
    import pymupdf  # noqa: F401
except ImportError:  # PyMuPDF < 1.24
    import fitz as pymupdf  # noqa: F401


def _area_conteudo(pagina) -> "pymupdf.Rect | None":
    retangulos = []
    for bloco in pagina.get_text("blocks"):
        retangulos.append(pymupdf.Rect(bloco[:4]))
    try:
        for d in pagina.get_drawings():
            retangulos.append(pymupdf.Rect(d["rect"]))
    except Exception:  # noqa: BLE001
        pass
    for info in pagina.get_image_info():
        retangulos.append(pymupdf.Rect(info["bbox"]))
    retangulos = [r for r in retangulos if not r.is_empty and r.is_valid]
    if not retangulos:
        return None
    area = retangulos[0]
    for r in retangulos[1:]:
        area |= r
    return area & pagina.rect


def paginas_png(pdf: Path, dpi: int = 140, recortar: bool = True, margem: float = 8) -> list[bytes]:
    """Cada página como PNG; com ``recortar`` corta as margens em branco."""
    imagens = []
    with pymupdf.open(pdf) as doc:
        for pagina in doc:
            clip = None
            if recortar:
                area = _area_conteudo(pagina)
                if area is not None:
                    clip = pymupdf.Rect(area.x0 - margem, area.y0 - margem,
                                        area.x1 + margem, area.y1 + margem) & pagina.rect
            pix = pagina.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            imagens.append(pix.tobytes("png"))
    return imagens


def numero_paginas(pdf: Path) -> int:
    with pymupdf.open(pdf) as doc:
        return doc.page_count
