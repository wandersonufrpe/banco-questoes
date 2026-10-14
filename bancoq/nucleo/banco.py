"""Arquivo SQLite do banco: conexão, esquema e migrações.

O banco fica numa pasta sincronizada (Google Drive / rclone). Por isso:

* o diário é ``journal_mode=DELETE`` (sem WAL): o arquivo ``-journal`` só existe
  durante uma escrita e é apagado em seguida;
* cada operação abre a conexão, faz o trabalho e fecha (conexões curtas).
"""

from __future__ import annotations

import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config_banco import ConfigBanco

VERSAO_ESQUEMA = 1
ARQUIVO_DB = "banco.sqlite3"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);

CREATE TABLE IF NOT EXISTS categorias (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL,
    pai_id  INTEGER REFERENCES categorias(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_categorias_pai ON categorias(pai_id);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY,
    nome  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS questoes (
    id              INTEGER PRIMARY KEY,
    tipo            TEXT NOT NULL CHECK (tipo IN ('discursiva','multipla','vf','curta')),
    enunciado       TEXT NOT NULL DEFAULT '',
    resposta_curta  TEXT NOT NULL DEFAULT '',
    resolucao       TEXT NOT NULL DEFAULT '',
    observacoes     TEXT NOT NULL DEFAULT '',
    dificuldade     INTEGER NOT NULL DEFAULT 3 CHECK (dificuldade BETWEEN 1 AND 5),
    fonte           TEXT NOT NULL DEFAULT '',
    ano             INTEGER,
    categoria_id    INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
    nao_embaralhar  INTEGER NOT NULL DEFAULT 0,
    criada_em       TEXT NOT NULL,
    alterada_em     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_questoes_categoria ON questoes(categoria_id);

CREATE TABLE IF NOT EXISTS itens (
    id          INTEGER PRIMARY KEY,
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL,
    texto       TEXT NOT NULL DEFAULT '',
    correta     INTEGER NOT NULL DEFAULT 0,
    comentario  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_itens_questao ON itens(questao_id);

CREATE TABLE IF NOT EXISTS questao_tags (
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (questao_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_questao_tags_tag ON questao_tags(tag_id);

CREATE TABLE IF NOT EXISTS imagens (
    id          INTEGER PRIMARY KEY,
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    item_id     INTEGER REFERENCES itens(id) ON DELETE CASCADE,
    arquivo     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_imagens_questao ON imagens(questao_id);

CREATE TABLE IF NOT EXISTS montagens (
    id           INTEGER PRIMARY KEY,
    nome         TEXT NOT NULL,
    dados        TEXT NOT NULL,
    criada_em    TEXT NOT NULL,
    alterada_em  TEXT NOT NULL
);
"""

ESQUEMA_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS questoes_fts USING fts5(
    enunciado, alternativas, resolucao, observacoes,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


class ErroBanco(Exception):
    pass


class ErroSomenteLeitura(ErroBanco):
    def __init__(self) -> None:
        super().__init__("O banco foi aberto somente para leitura.")


def agora_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def sem_acentos(texto: str | None) -> str:
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


_fts5: bool | None = None


def fts5_disponivel() -> bool:
    global _fts5
    if _fts5 is None:
        try:
            c = sqlite3.connect(":memory:")
            c.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
            c.close()
            _fts5 = True
        except sqlite3.Error:
            _fts5 = False
    return _fts5


class Banco:
    """Uma pasta de banco de questões."""

    def __init__(self, pasta: Path | str, somente_leitura: bool = False):
        self.pasta = Path(pasta)
        self.somente_leitura = somente_leitura
        if not self.caminho_db.exists():
            raise ErroBanco(f"Não há banco de questões em {self.pasta}.")
        self._usar_fts = False
        self._preparar()

    # -- caminhos -------------------------------------------------------------
    @property
    def caminho_db(self) -> Path:
        return self.pasta / ARQUIVO_DB

    @property
    def pasta_midia(self) -> Path:
        return self.pasta / "midia"

    @property
    def pasta_modelos(self) -> Path:
        return self.pasta / "modelos"

    @property
    def pasta_backups(self) -> Path:
        return self.pasta / "backups"

    @property
    def nome(self) -> str:
        return self.pasta.name

    @property
    def usar_fts(self) -> bool:
        return self._usar_fts

    @staticmethod
    def e_banco(pasta: Path | str) -> bool:
        return (Path(pasta) / ARQUIVO_DB).is_file()

    # -- criação --------------------------------------------------------------
    @classmethod
    def criar(cls, pasta: Path | str) -> "Banco":
        pasta = Path(pasta)
        if cls.e_banco(pasta):
            raise ErroBanco(f"Já existe um banco em {pasta}.")
        pasta.mkdir(parents=True, exist_ok=True)
        for sub in ("midia", "modelos", "backups"):
            (pasta / sub).mkdir(exist_ok=True)
        conn = sqlite3.connect(pasta / ARQUIVO_DB)
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.executescript(ESQUEMA)
            if fts5_disponivel():
                conn.executescript(ESQUEMA_FTS)
            conn.execute(f"PRAGMA user_version={VERSAO_ESQUEMA}")
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('criado_em', ?)", (agora_iso(),))
            conn.commit()
        finally:
            conn.close()
        from .modelos_prova import copiar_modelo_generico

        copiar_modelo_generico(pasta / "modelos")
        ConfigBanco().salvar(pasta)
        return cls(pasta)

    # -- conexão ----------------------------------------------------------------
    def _abrir(self) -> sqlite3.Connection:
        if self.somente_leitura:
            uri = self.caminho_db.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
        else:
            conn = sqlite3.connect(self.caminho_db, timeout=10, isolation_level=None)
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=FULL")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.create_function("normal", 1, sem_acentos, deterministic=True)
        return conn

    @contextmanager
    def conectar(self, escrita: bool = False) -> Iterator[sqlite3.Connection]:
        """Abre uma conexão curta. Com ``escrita=True`` tudo vira uma transação."""
        if escrita and self.somente_leitura:
            raise ErroSomenteLeitura()
        conn = self._abrir()
        try:
            if escrita:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if escrita:
                conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _preparar(self) -> None:
        """Confere a versão do esquema e se a busca FTS5 está disponível."""
        with self.conectar() as c:
            versao = c.execute("PRAGMA user_version").fetchone()[0]
            tem_fts = c.execute(
                "SELECT 1 FROM sqlite_master WHERE name='questoes_fts'"
            ).fetchone() is not None
        if versao > VERSAO_ESQUEMA:
            raise ErroBanco(
                "Este banco foi criado por uma versão mais nova do aplicativo. "
                "Atualize o aplicativo para abri-lo."
            )
        if versao < VERSAO_ESQUEMA and not self.somente_leitura:
            self._migrar(versao)
        if fts5_disponivel():
            if not tem_fts and not self.somente_leitura:
                self.reconstruir_fts()
                tem_fts = True
            self._usar_fts = tem_fts and not self._fts_desatualizado()
            if not self._usar_fts and tem_fts and not self.somente_leitura:
                self.reconstruir_fts()
                self._usar_fts = True

    def _migrar(self, versao: int) -> None:  # pragma: no cover - só há a versão 1
        with self.conectar() as c:
            c.executescript(ESQUEMA)
            c.execute(f"PRAGMA user_version={VERSAO_ESQUEMA}")

    def _fts_desatualizado(self) -> bool:
        with self.conectar() as c:
            r = c.execute("SELECT valor FROM meta WHERE chave='fts_desatualizado'").fetchone()
        return bool(r and r[0] == "1")

    def reconstruir_fts(self) -> None:
        from .repositorio import textos_fts_linha

        with self.conectar(escrita=True) as c:
            c.execute(ESQUEMA_FTS.strip().rstrip(";"))
            c.execute("DELETE FROM questoes_fts")
            for q in c.execute("SELECT * FROM questoes").fetchall():
                itens = c.execute(
                    "SELECT texto, comentario FROM itens WHERE questao_id=? ORDER BY ordem", (q["id"],)
                ).fetchall()
                c.execute(
                    "INSERT INTO questoes_fts(rowid, enunciado, alternativas, resolucao, observacoes)"
                    " VALUES (?,?,?,?,?)",
                    (q["id"], *textos_fts_linha(q, itens)),
                )
            c.execute("DELETE FROM meta WHERE chave='fts_desatualizado'")

    # -- utilidades ---------------------------------------------------------------
    def copiar_arquivo_db(self, destino: Path) -> None:
        """Cópia consistente do SQLite (usa a API de backup do SQLite)."""
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        origem = self._abrir()
        try:
            alvo = sqlite3.connect(destino)
            try:
                origem.backup(alvo)
                alvo.execute("PRAGMA journal_mode=DELETE")
            finally:
                alvo.close()
        finally:
            origem.close()
