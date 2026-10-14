"""Imagens das questões.

Cada imagem é guardada em ``midia/`` com o nome dado pelo hash (SHA-256,
16 primeiros dígitos hexadecimais) do conteúdo. No texto da questão ela
aparece como o marcador ``[[img:ID]]`` ou ``[[img:ID|0.5]]``, em que o número
é a largura como fração da largura da linha (também aceita ``|50%``).

Imagens inseridas numa questão ainda não salva ficam numa pasta temporária
("pendentes") e só são copiadas para ``midia/`` quando a questão é salva.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

EXTENSOES = ("png", "jpg", "pdf")
LARGURA_PADRAO = 0.6

RE_MARCADOR = re.compile(
    r"\[\[img:([0-9a-fA-F]{6,64})(?:\s*\|\s*([0-9]*[.,]?[0-9]+)\s*(%?))?\s*\]\]"
)


class ErroMidia(Exception):
    pass


def identificar_formato(dados: bytes) -> str | None:
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if dados[:1024].lstrip().startswith(b"%PDF"):
        return "pdf"
    return None


def calcular_id(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()[:16]


def largura_de(match: re.Match) -> float:
    """Largura (fração da linha) de um marcador encontrado por RE_MARCADOR."""
    numero, porcento = match.group(2), match.group(3)
    if not numero:
        return LARGURA_PADRAO
    valor = float(numero.replace(",", "."))
    if porcento:
        valor /= 100.0
    return max(0.05, min(valor, 1.0))


def ids_no_texto(texto: str) -> list[str]:
    vistos: list[str] = []
    for m in RE_MARCADOR.finditer(texto or ""):
        ident = m.group(1).lower()
        if ident not in vistos:
            vistos.append(ident)
    return vistos


def marcador(ident: str, largura: float = LARGURA_PADRAO) -> str:
    return f"[[img:{ident}|{largura:g}]]"


def formatar_largura(largura: float) -> str:
    return f"{largura:.2f}".rstrip("0").rstrip(".")


class GerenciadorMidia:
    """Resolve marcadores para arquivos e cuida das imagens pendentes."""

    def __init__(self, pasta_midia: Path, pasta_temp: Path):
        self.pasta_midia = Path(pasta_midia)
        self.pasta_pendentes = Path(pasta_temp) / "pendentes"
        self.pasta_cache = Path(pasta_temp) / "cache-previa"
        self._pendentes: dict[str, Path] = {}

    # -- consulta -------------------------------------------------------
    def caminho(self, ident: str) -> Path | None:
        ident = ident.lower()
        if ident in self._pendentes and self._pendentes[ident].exists():
            return self._pendentes[ident]
        for ext in EXTENSOES:
            p = self.pasta_midia / f"{ident}.{ext}"
            if p.exists():
                return p
        # marcador abreviado: procura arquivo que comece com o prefixo
        if len(ident) < 16 and self.pasta_midia.exists():
            for p in self.pasta_midia.glob(f"{ident}*"):
                if p.suffix.lstrip(".") in EXTENSOES:
                    return p
        return None

    def e_pendente(self, ident: str) -> bool:
        return ident.lower() in self._pendentes

    def caminho_previa(self, ident: str) -> Path | None:
        """Arquivo que um navegador consegue mostrar (PDF vira PNG em cache)."""
        p = self.caminho(ident)
        if p is None or p.suffix.lower() != ".pdf":
            return p
        destino = self.pasta_cache / f"{p.stem}.png"
        if not destino.exists():
            try:
                from .pdf import pymupdf

                self.pasta_cache.mkdir(parents=True, exist_ok=True)
                with pymupdf.open(p) as doc:
                    pix = doc[0].get_pixmap(dpi=110)
                    pix.save(destino)
            except Exception:
                return None
        return destino

    # -- inserção ---------------------------------------------------------
    def adicionar_bytes(self, dados: bytes) -> str:
        ext = identificar_formato(dados)
        if ext is None:
            raise ErroMidia("Formato não suportado. Use PNG, JPG ou PDF.")
        ident = calcular_id(dados)
        if self.caminho(ident) is not None:
            return ident
        self.pasta_pendentes.mkdir(parents=True, exist_ok=True)
        destino = self.pasta_pendentes / f"{ident}.{ext}"
        destino.write_bytes(dados)
        self._pendentes[ident] = destino
        return ident

    def adicionar_arquivo(self, arquivo: Path | str) -> str:
        arquivo = Path(arquivo)
        try:
            dados = arquivo.read_bytes()
        except OSError as e:
            raise ErroMidia(f"Não foi possível ler {arquivo.name}: {e}") from e
        if identificar_formato(dados) is None:
            raise ErroMidia(f"{arquivo.name}: formato não suportado. Use PNG, JPG ou PDF.")
        return self.adicionar_bytes(dados)

    # -- gravação -----------------------------------------------------------
    def gravar_pendentes(self, idents: list[str] | set[str]) -> list[str]:
        """Copia para midia/ as imagens pendentes usadas; devolve os nomes de arquivo."""
        nomes = []
        for ident in idents:
            ident = ident.lower()
            origem = self._pendentes.get(ident)
            if origem is not None and origem.exists():
                self.pasta_midia.mkdir(parents=True, exist_ok=True)
                destino = self.pasta_midia / origem.name
                if not destino.exists():
                    tmp = destino.with_suffix(destino.suffix + ".tmp")
                    shutil.copyfile(origem, tmp)
                    tmp.replace(destino)
                self._pendentes.pop(ident, None)
                nomes.append(destino.name)
            else:
                p = self.caminho(ident)
                if p is not None:
                    nomes.append(p.name)
        return nomes

    def descartar_pendentes(self) -> None:
        for p in self._pendentes.values():
            try:
                p.unlink()
            except OSError:
                pass
        self._pendentes.clear()
