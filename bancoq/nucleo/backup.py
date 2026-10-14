"""Backups do banco em .zip (automático ao abrir, manual, restauração, exportar/importar)."""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .banco import ARQUIVO_DB, Banco
from .config_banco import ARQUIVO_CONFIG
from .trava import nome_computador

RE_BACKUP = re.compile(r"^backup-(\d{8})-(\d{6})(?:-(.*))?\.zip$")
PASTAS_INCLUIDAS = ("midia", "modelos")


@dataclass
class InfoBackup:
    caminho: Path
    quando: datetime
    computador: str
    tamanho: int

    @property
    def descricao(self) -> str:
        mb = self.tamanho / (1024 * 1024)
        return f"{self.quando.strftime('%d/%m/%Y %H:%M:%S')} — {self.computador} — {mb:.1f} MB"


def _seguro(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", texto).strip("_")[:40] or "pc"


def escrever_zip(banco: Banco, destino: Path) -> Path:
    """Escreve banco + configurações + modelos + mídia num .zip (cópia consistente do SQLite)."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = destino.with_name(destino.name + ".parcial")
    with tempfile.TemporaryDirectory(prefix="bancoq-backup-") as tmp:
        copia_db = Path(tmp) / ARQUIVO_DB
        banco.copiar_arquivo_db(copia_db)
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(copia_db, ARQUIVO_DB)
            cfg = banco.pasta / ARQUIVO_CONFIG
            if cfg.exists():
                z.write(cfg, ARQUIVO_CONFIG)
            for sub in PASTAS_INCLUIDAS:
                pasta = banco.pasta / sub
                if not pasta.is_dir():
                    continue
                for arq in sorted(pasta.rglob("*")):
                    if arq.is_file() and not arq.name.endswith((".tmp", ".parcial")):
                        compressao = zipfile.ZIP_STORED if arq.suffix.lower() in (".png", ".jpg", ".pdf") \
                            else zipfile.ZIP_DEFLATED
                        z.write(arq, arq.relative_to(banco.pasta).as_posix(), compress_type=compressao)
    tmp_zip.replace(destino)
    return destino


def criar_backup(banco: Banco, manter: int = 10, sufixo: str = "") -> Path:
    agora = datetime.now()
    nome = f"backup-{agora:%Y%m%d-%H%M%S}-{_seguro(nome_computador())}{('-' + sufixo) if sufixo else ''}.zip"
    destino = banco.pasta_backups / nome
    n = 1
    while destino.exists():
        destino = banco.pasta_backups / nome.replace(".zip", f"-{n}.zip")
        n += 1
    escrever_zip(banco, destino)
    podar_backups(banco, manter)
    return destino


def listar_backups(banco: Banco) -> list[InfoBackup]:
    res = []
    if not banco.pasta_backups.is_dir():
        return res
    for p in banco.pasta_backups.glob("backup-*.zip"):
        m = RE_BACKUP.match(p.name)
        if not m:
            continue
        try:
            quando = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        res.append(InfoBackup(p, quando, (m.group(3) or "").replace("_", " "), p.stat().st_size))
    res.sort(key=lambda b: (b.quando, b.caminho.name), reverse=True)
    return res


def podar_backups(banco: Banco, manter: int) -> list[Path]:
    removidos = []
    for b in listar_backups(banco)[max(1, manter):]:
        try:
            b.caminho.unlink()
            removidos.append(b.caminho)
        except OSError:
            pass
    return removidos


class ErroBackup(Exception):
    pass


def _validar_zip(z: zipfile.ZipFile) -> None:
    nomes = z.namelist()
    if ARQUIVO_DB not in nomes:
        raise ErroBackup("O arquivo não é um backup do Banco de Questões (falta banco.sqlite3).")
    for n in nomes:
        p = Path(n)
        if p.is_absolute() or ".." in p.parts:
            raise ErroBackup(f"Caminho inválido dentro do .zip: {n}")
        if p.parts[0] not in (ARQUIVO_DB, ARQUIVO_CONFIG, *PASTAS_INCLUIDAS):
            raise ErroBackup(f"Arquivo inesperado dentro do .zip: {n}")


def _conferir_sqlite(caminho: Path) -> None:
    try:
        c = sqlite3.connect(caminho)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.execute("SELECT count(*) FROM questoes").fetchone()
        c.close()
    except sqlite3.Error as e:
        raise ErroBackup(f"O banco dentro do .zip está danificado: {e}") from e
    if ok != "ok":
        raise ErroBackup(f"O banco dentro do .zip está danificado: {ok}")


def restaurar_backup(banco: Banco, arquivo_zip: Path, manter: int = 10) -> Path:
    """Restaura um backup sobre o banco atual. Antes, guarda o estado atual num backup.

    Devolve o caminho do backup de segurança feito antes de restaurar.
    """
    arquivo_zip = Path(arquivo_zip)
    with zipfile.ZipFile(arquivo_zip) as z:
        _validar_zip(z)
        with tempfile.TemporaryDirectory(prefix="bancoq-restaurar-") as tmp:
            z.extractall(tmp)
            _conferir_sqlite(Path(tmp) / ARQUIVO_DB)
            seguranca = criar_backup(banco, manter + 1, "antes-de-restaurar")
            origem = Path(tmp)
            alvo_db = banco.caminho_db
            temp_db = alvo_db.with_name(alvo_db.name + ".restaurando")
            shutil.copyfile(origem / ARQUIVO_DB, temp_db)
            temp_db.replace(alvo_db)
            if (origem / ARQUIVO_CONFIG).exists():
                shutil.copyfile(origem / ARQUIVO_CONFIG, banco.pasta / ARQUIVO_CONFIG)
            for sub in PASTAS_INCLUIDAS:
                if (origem / sub).is_dir():
                    for arq in (origem / sub).rglob("*"):
                        if arq.is_file():
                            destino = banco.pasta / arq.relative_to(origem)
                            destino.parent.mkdir(parents=True, exist_ok=True)
                            # mídia tem nome = hash: só copia o que falta; modelos são substituídos
                            if sub == "midia" and destino.exists():
                                continue
                            shutil.copyfile(arq, destino)
    return seguranca


def importar_banco_zip(arquivo_zip: Path, pasta_destino: Path) -> Path:
    """Extrai um banco exportado numa pasta nova (vazia)."""
    pasta_destino = Path(pasta_destino)
    if Banco.e_banco(pasta_destino):
        raise ErroBackup("A pasta de destino já contém um banco. Escolha uma pasta vazia.")
    with zipfile.ZipFile(arquivo_zip) as z:
        _validar_zip(z)
        pasta_destino.mkdir(parents=True, exist_ok=True)
        z.extractall(pasta_destino)
    _conferir_sqlite(pasta_destino / ARQUIVO_DB)
    for sub in ("midia", "modelos", "backups"):
        (pasta_destino / sub).mkdir(exist_ok=True)
    return pasta_destino
