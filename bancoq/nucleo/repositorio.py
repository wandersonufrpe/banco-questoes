"""Operações sobre as questões, categorias, tags e montagens salvas."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Iterable

from .banco import Banco, ErroBanco, agora_iso, sem_acentos
from .entidades import Categoria, Item, Questao, ResumoQuestao, Tag
from .midia import GerenciadorMidia, ids_no_texto

SEP_TAGS = "\x1f"


@dataclass
class CategoriaNova:
    """Categoria criada no seletor e ainda não gravada.

    ``nomes`` é o caminho a partir de ``pai_id`` (que já existe no banco ou é
    ``None`` para a raiz). As categorias só são criadas quando a questão é salva.
    """

    pai_id: int | None
    nomes: list[str]


@dataclass
class Filtro:
    categoria_id: int | None = None
    incluir_subcategorias: bool = True
    sem_categoria: bool = False
    tags: list[str] = field(default_factory=list)
    tags_modo: str = "todas"            # "todas" ou "qualquer"
    tipos: list[str] = field(default_factory=list)
    dif_min: int = 1
    dif_max: int = 5
    fonte: str = ""
    ano_min: int | None = None
    ano_max: int | None = None
    texto: str = ""
    excluir_ids: list[int] = field(default_factory=list)

    def para_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def de_dict(cls, d: dict) -> "Filtro":
        f = cls()
        for k, v in (d or {}).items():
            if hasattr(f, k):
                setattr(f, k, v)
        return f


def textos_fts_linha(q, itens) -> tuple[str, str, str, str]:
    """Textos indexados na busca (aceita sqlite3.Row ou Questao)."""
    partes = [f"{i['texto']}\n{i['comentario']}" for i in itens]
    partes.append(q["resposta_curta"])
    return q["enunciado"], "\n".join(partes), q["resolucao"], q["observacoes"]


def consulta_fts(texto: str) -> str:
    termos = re.findall(r"\w+", texto or "")
    return " ".join(f'"{t}"*' for t in termos)


class Repositorio:
    def __init__(self, banco: Banco, midia: GerenciadorMidia):
        self.banco = banco
        self.midia = midia

    @property
    def somente_leitura(self) -> bool:
        return self.banco.somente_leitura

    # =====================================================================
    # Questões
    # =====================================================================
    def salvar_questao(self, q: Questao, categoria_nova: CategoriaNova | None = None) -> int:
        """Grava a questão (nova ou existente) numa única transação."""
        return self.salvar_questoes([(q, categoria_nova)])[0]

    def salvar_questoes(self, lista: list[tuple[Questao, CategoriaNova | None]]) -> list[int]:
        """Grava várias questões numa única transação (tudo ou nada)."""
        with self.banco.conectar(escrita=True) as c:
            return [self._salvar(c, q, cat) for q, cat in lista]

    def _salvar(self, c: sqlite3.Connection, q: Questao, categoria_nova: CategoriaNova | None) -> int:
        q.tipo = q.tipo if q.tipo in ("discursiva", "multipla", "vf", "curta") else "discursiva"
        agora = agora_iso()
        if categoria_nova is not None and categoria_nova.nomes:
            q.categoria_id = self._garantir_caminho(c, categoria_nova.pai_id, categoria_nova.nomes)
        if q.categoria_id is not None and not c.execute(
            "SELECT 1 FROM categorias WHERE id=?", (q.categoria_id,)
        ).fetchone():
            q.categoria_id = None
        valores = (
            q.tipo, q.enunciado, q.resposta_curta if q.tipo == "curta" else "",
            q.resolucao, q.observacoes, int(min(5, max(1, q.dificuldade))),
            q.fonte.strip(), q.ano, q.categoria_id, int(bool(q.nao_embaralhar)),
        )
        if q.id is None:
            cur = c.execute(
                "INSERT INTO questoes (tipo, enunciado, resposta_curta, resolucao, observacoes,"
                " dificuldade, fonte, ano, categoria_id, nao_embaralhar, criada_em, alterada_em)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (*valores, agora, agora),
            )
            q.id = cur.lastrowid
            q.criada_em = agora
        else:
            cur = c.execute(
                "UPDATE questoes SET tipo=?, enunciado=?, resposta_curta=?, resolucao=?,"
                " observacoes=?, dificuldade=?, fonte=?, ano=?, categoria_id=?,"
                " nao_embaralhar=?, alterada_em=? WHERE id=?",
                (*valores, agora, q.id),
            )
            if cur.rowcount == 0:
                raise ErroBanco(f"A questão {q.id} não existe mais no banco.")
        q.alterada_em = agora

        # itens (alternativas/afirmativas)
        c.execute("DELETE FROM itens WHERE questao_id=?", (q.id,))
        itens = q.itens_validos()
        for ordem, item in enumerate(itens):
            cur = c.execute(
                "INSERT INTO itens (questao_id, ordem, texto, correta, comentario) VALUES (?,?,?,?,?)",
                (q.id, ordem, item.texto, int(bool(item.correta)), item.comentario),
            )
            item.id = cur.lastrowid
        if not q.usa_itens:
            q.itens = []

        # tags
        c.execute("DELETE FROM questao_tags WHERE questao_id=?", (q.id,))
        nomes_tags = []
        for nome in q.tags:
            nome = nome.strip()
            if nome and nome.casefold() not in {n.casefold() for n in nomes_tags}:
                nomes_tags.append(nome)
        for nome in nomes_tags:
            tag_id = self._garantir_tag(c, nome)
            c.execute("INSERT OR IGNORE INTO questao_tags VALUES (?,?)", (q.id, tag_id))
        q.tags = nomes_tags

        # imagens: grava as pendentes em midia/ e registra a ligação
        c.execute("DELETE FROM imagens WHERE questao_id=?", (q.id,))
        textos_questao = [q.enunciado, q.resolucao, q.resposta_curta]
        ligacoes: list[tuple[int | None, str]] = []
        for t in textos_questao:
            ligacoes += [(None, i) for i in ids_no_texto(t)]
        for item in itens:
            ligacoes += [(item.id, i) for i in ids_no_texto(item.texto + "\n" + item.comentario)]
        self.midia.gravar_pendentes({i for _, i in ligacoes})
        vistos = set()
        for item_id, ident in ligacoes:
            p = self.midia.caminho(ident)
            if p is None or (item_id, p.name) in vistos:
                continue
            vistos.add((item_id, p.name))
            c.execute(
                "INSERT INTO imagens (questao_id, item_id, arquivo) VALUES (?,?,?)",
                (q.id, item_id, p.name),
            )

        self._atualizar_fts(c, q.id)
        return q.id

    def _atualizar_fts(self, c: sqlite3.Connection, qid: int) -> None:
        if not self.banco.usar_fts:
            try:
                c.execute("INSERT OR REPLACE INTO meta VALUES ('fts_desatualizado', '1')")
            except sqlite3.Error:
                pass
            return
        c.execute("DELETE FROM questoes_fts WHERE rowid=?", (qid,))
        q = c.execute("SELECT * FROM questoes WHERE id=?", (qid,)).fetchone()
        if q is None:
            return
        itens = c.execute(
            "SELECT texto, comentario FROM itens WHERE questao_id=? ORDER BY ordem", (qid,)
        ).fetchall()
        c.execute(
            "INSERT INTO questoes_fts(rowid, enunciado, alternativas, resolucao, observacoes)"
            " VALUES (?,?,?,?,?)",
            (qid, *textos_fts_linha(q, itens)),
        )

    def obter_questao(self, qid: int) -> Questao | None:
        with self.banco.conectar() as c:
            return self._ler_questao(c, qid)

    def obter_questoes(self, ids: Iterable[int]) -> dict[int, Questao]:
        res = {}
        with self.banco.conectar() as c:
            for qid in ids:
                q = self._ler_questao(c, qid)
                if q is not None:
                    res[qid] = q
        return res

    def _ler_questao(self, c: sqlite3.Connection, qid: int) -> Questao | None:
        r = c.execute("SELECT * FROM questoes WHERE id=?", (qid,)).fetchone()
        if r is None:
            return None
        itens = [
            Item(texto=i["texto"], correta=bool(i["correta"]), comentario=i["comentario"], id=i["id"])
            for i in c.execute("SELECT * FROM itens WHERE questao_id=? ORDER BY ordem", (qid,))
        ]
        tags = [
            t[0]
            for t in c.execute(
                "SELECT t.nome FROM questao_tags qt JOIN tags t ON t.id=qt.tag_id"
                " WHERE qt.questao_id=? ORDER BY t.nome COLLATE NOCASE",
                (qid,),
            )
        ]
        return Questao(
            id=r["id"], tipo=r["tipo"], enunciado=r["enunciado"], itens=itens,
            resposta_curta=r["resposta_curta"], resolucao=r["resolucao"],
            observacoes=r["observacoes"], dificuldade=r["dificuldade"], fonte=r["fonte"],
            ano=r["ano"], categoria_id=r["categoria_id"], tags=tags,
            nao_embaralhar=bool(r["nao_embaralhar"]), criada_em=r["criada_em"],
            alterada_em=r["alterada_em"],
        )

    def excluir_questao(self, qid: int) -> None:
        with self.banco.conectar(escrita=True) as c:
            c.execute("DELETE FROM questoes WHERE id=?", (qid,))
            if self.banco.usar_fts:
                c.execute("DELETE FROM questoes_fts WHERE rowid=?", (qid,))

    def contar_questoes(self) -> int:
        with self.banco.conectar() as c:
            return c.execute("SELECT count(*) FROM questoes").fetchone()[0]

    def imagens_da_questao(self, qid: int) -> list[tuple[int | None, str]]:
        with self.banco.conectar() as c:
            return [
                (r["item_id"], r["arquivo"])
                for r in c.execute("SELECT item_id, arquivo FROM imagens WHERE questao_id=?", (qid,))
            ]

    # -- busca ------------------------------------------------------------------
    def _where(self, c: sqlite3.Connection, f: Filtro) -> tuple[str, list]:
        cond: list[str] = []
        par: list = []
        if f.sem_categoria:
            cond.append("q.categoria_id IS NULL")
        elif f.categoria_id is not None:
            ids = [f.categoria_id]
            if f.incluir_subcategorias:
                ids = sorted(self._descendentes(c, f.categoria_id) | {f.categoria_id})
            cond.append(f"q.categoria_id IN ({','.join('?' * len(ids))})")
            par += ids
        nomes = [t.strip() for t in f.tags if t.strip()]
        if nomes:
            ids_tags = []
            for nome in nomes:
                r = c.execute("SELECT id FROM tags WHERE nome=? COLLATE NOCASE", (nome,)).fetchone()
                if r:
                    ids_tags.append(r[0])
                elif f.tags_modo == "todas":
                    cond.append("0")
            if f.tags_modo == "todas":
                for tid in ids_tags:
                    cond.append(
                        "EXISTS (SELECT 1 FROM questao_tags qt WHERE qt.questao_id=q.id AND qt.tag_id=?)"
                    )
                    par.append(tid)
            elif ids_tags:
                cond.append(
                    "EXISTS (SELECT 1 FROM questao_tags qt WHERE qt.questao_id=q.id"
                    f" AND qt.tag_id IN ({','.join('?' * len(ids_tags))}))"
                )
                par += ids_tags
            else:
                cond.append("0")
        if f.tipos:
            cond.append(f"q.tipo IN ({','.join('?' * len(f.tipos))})")
            par += list(f.tipos)
        if f.dif_min > 1 or f.dif_max < 5:
            cond.append("q.dificuldade BETWEEN ? AND ?")
            par += [f.dif_min, f.dif_max]
        if f.fonte.strip():
            cond.append("normal(q.fonte) LIKE ?")
            par.append(f"%{sem_acentos(f.fonte.strip())}%")
        if f.ano_min is not None:
            cond.append("q.ano >= ?")
            par.append(f.ano_min)
        if f.ano_max is not None:
            cond.append("q.ano <= ?")
            par.append(f.ano_max)
        if f.texto.strip():
            consulta = consulta_fts(f.texto)
            if consulta and self.banco.usar_fts:
                cond.append("q.id IN (SELECT rowid FROM questoes_fts WHERE questoes_fts MATCH ?)")
                par.append(consulta)
            else:
                for termo in re.findall(r"\w+", f.texto):
                    p = f"%{sem_acentos(termo)}%"
                    cond.append(
                        "(normal(q.enunciado) LIKE ? OR normal(q.resolucao) LIKE ?"
                        " OR normal(q.observacoes) LIKE ? OR normal(q.resposta_curta) LIKE ?"
                        " OR EXISTS (SELECT 1 FROM itens i WHERE i.questao_id=q.id"
                        " AND (normal(i.texto) LIKE ? OR normal(i.comentario) LIKE ?)))"
                    )
                    par += [p] * 6
        if f.excluir_ids:
            cond.append(f"q.id NOT IN ({','.join('?' * len(f.excluir_ids))})")
            par += list(f.excluir_ids)
        return (" WHERE " + " AND ".join(cond)) if cond else "", par

    def buscar(self, f: Filtro | None = None) -> list[ResumoQuestao]:
        f = f or Filtro()
        with self.banco.conectar() as c:
            where, par = self._where(c, f)
            linhas = c.execute(
                "SELECT q.id, q.tipo, q.enunciado, q.dificuldade, q.fonte, q.ano, q.categoria_id,"
                " q.alterada_em, (SELECT group_concat(t.nome, ?) FROM questao_tags qt"
                " JOIN tags t ON t.id=qt.tag_id WHERE qt.questao_id=q.id) AS tags"
                f" FROM questoes q{where} ORDER BY q.id DESC",
                [SEP_TAGS, *par],
            ).fetchall()
        return [
            ResumoQuestao(
                id=r["id"], tipo=r["tipo"], enunciado=r["enunciado"], dificuldade=r["dificuldade"],
                fonte=r["fonte"], ano=r["ano"], categoria_id=r["categoria_id"],
                tags=sorted(r["tags"].split(SEP_TAGS), key=str.casefold) if r["tags"] else [],
                alterada_em=r["alterada_em"],
            )
            for r in linhas
        ]

    def ids_filtrados(self, f: Filtro) -> list[int]:
        with self.banco.conectar() as c:
            where, par = self._where(c, f)
            return [r[0] for r in c.execute(f"SELECT q.id FROM questoes q{where} ORDER BY q.id", par)]

    def enunciados(self) -> list[tuple[int, str]]:
        with self.banco.conectar() as c:
            return [(r[0], r[1]) for r in c.execute("SELECT id, enunciado FROM questoes")]

    def fontes(self) -> list[str]:
        with self.banco.conectar() as c:
            return [
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT fonte FROM questoes WHERE fonte<>'' ORDER BY fonte COLLATE NOCASE"
                )
            ]

    # =====================================================================
    # Categorias
    # =====================================================================
    def categorias(self) -> list[Categoria]:
        with self.banco.conectar() as c:
            return [
                Categoria(r["id"], r["nome"], r["pai_id"])
                for r in c.execute("SELECT * FROM categorias ORDER BY nome COLLATE NOCASE")
            ]

    def caminhos_categorias(self) -> dict[int, str]:
        cats = {c.id: c for c in self.categorias()}
        caminhos: dict[int, str] = {}

        def caminho(cid: int, visitados: set) -> str:
            if cid in caminhos:
                return caminhos[cid]
            cat = cats[cid]
            if cat.pai_id is None or cat.pai_id not in cats or cat.pai_id in visitados:
                s = cat.nome
            else:
                s = caminho(cat.pai_id, visitados | {cid}) + " > " + cat.nome
            caminhos[cid] = s
            return s

        for cid in cats:
            caminho(cid, set())
        return caminhos

    def contagem_por_categoria(self) -> dict[int | None, int]:
        with self.banco.conectar() as c:
            return {
                r[0]: r[1]
                for r in c.execute("SELECT categoria_id, count(*) FROM questoes GROUP BY categoria_id")
            }

    @staticmethod
    def _descendentes(c: sqlite3.Connection, cid: int) -> set[int]:
        linhas = c.execute(
            "WITH RECURSIVE d(id) AS (SELECT id FROM categorias WHERE pai_id=?"
            " UNION SELECT c.id FROM categorias c JOIN d ON c.pai_id=d.id) SELECT id FROM d",
            (cid,),
        ).fetchall()
        return {r[0] for r in linhas}

    def descendentes(self, cid: int) -> set[int]:
        with self.banco.conectar() as c:
            return self._descendentes(c, cid)

    @staticmethod
    def _filho(c: sqlite3.Connection, pai_id: int | None, nome: str) -> int | None:
        if pai_id is None:
            r = c.execute(
                "SELECT id FROM categorias WHERE pai_id IS NULL AND nome=? COLLATE NOCASE", (nome,)
            ).fetchone()
        else:
            r = c.execute(
                "SELECT id FROM categorias WHERE pai_id=? AND nome=? COLLATE NOCASE", (pai_id, nome)
            ).fetchone()
        return r[0] if r else None

    def _garantir_caminho(self, c: sqlite3.Connection, pai_id: int | None, nomes: list[str]) -> int | None:
        atual = pai_id
        for nome in nomes:
            nome = nome.strip()
            if not nome:
                continue
            existente = self._filho(c, atual, nome)
            if existente is None:
                existente = c.execute(
                    "INSERT INTO categorias (nome, pai_id) VALUES (?,?)", (nome, atual)
                ).lastrowid
            atual = existente
        return atual

    def criar_categoria(self, nome: str, pai_id: int | None = None) -> int:
        nome = nome.strip()
        if not nome:
            raise ErroBanco("O nome da categoria não pode ficar vazio.")
        with self.banco.conectar(escrita=True) as c:
            if self._filho(c, pai_id, nome) is not None:
                raise ErroBanco(f"Já existe a categoria “{nome}” neste nível.")
            return c.execute("INSERT INTO categorias (nome, pai_id) VALUES (?,?)", (nome, pai_id)).lastrowid

    def renomear_categoria(self, cid: int, nome: str) -> None:
        nome = nome.strip()
        if not nome:
            raise ErroBanco("O nome da categoria não pode ficar vazio.")
        with self.banco.conectar(escrita=True) as c:
            r = c.execute("SELECT pai_id FROM categorias WHERE id=?", (cid,)).fetchone()
            if r is None:
                raise ErroBanco("Categoria não encontrada.")
            outro = self._filho(c, r[0], nome)
            if outro is not None and outro != cid:
                raise ErroBanco(f"Já existe a categoria “{nome}” neste nível. Use “Mesclar”.")
            c.execute("UPDATE categorias SET nome=? WHERE id=?", (nome, cid))

    def mover_categoria(self, cid: int, novo_pai: int | None) -> None:
        with self.banco.conectar(escrita=True) as c:
            if novo_pai is not None and (novo_pai == cid or novo_pai in self._descendentes(c, cid)):
                raise ErroBanco("Uma categoria não pode ficar dentro de si mesma.")
            nome = c.execute("SELECT nome FROM categorias WHERE id=?", (cid,)).fetchone()[0]
            outro = self._filho(c, novo_pai, nome)
            if outro is not None and outro != cid:
                self._mesclar(c, cid, outro)
            else:
                c.execute("UPDATE categorias SET pai_id=? WHERE id=?", (novo_pai, cid))

    def mesclar_categorias(self, origem: int, destino: int) -> None:
        """Move questões e subcategorias de ``origem`` para ``destino`` e apaga ``origem``."""
        if origem == destino:
            return
        with self.banco.conectar(escrita=True) as c:
            if destino in self._descendentes(c, origem):
                raise ErroBanco("Não é possível mesclar uma categoria com uma subcategoria dela.")
            self._mesclar(c, origem, destino)

    def _mesclar(self, c: sqlite3.Connection, origem: int, destino: int | None) -> None:
        c.execute("UPDATE questoes SET categoria_id=? WHERE categoria_id=?", (destino, origem))
        for filho_id, nome in c.execute(
            "SELECT id, nome FROM categorias WHERE pai_id=?", (origem,)
        ).fetchall():
            igual = self._filho(c, destino, nome)
            if igual is not None and igual != filho_id:
                self._mesclar(c, filho_id, igual)
            else:
                c.execute("UPDATE categorias SET pai_id=? WHERE id=?", (destino, filho_id))
        c.execute("DELETE FROM categorias WHERE id=?", (origem,))

    def excluir_categoria(self, cid: int) -> None:
        """Exclui a categoria; questões e subcategorias sobem para a categoria-mãe."""
        with self.banco.conectar(escrita=True) as c:
            r = c.execute("SELECT pai_id FROM categorias WHERE id=?", (cid,)).fetchone()
            if r is None:
                return
            self._mesclar(c, cid, r[0])

    def caminho_para_ids(self, nomes: list[str]) -> int | None:
        """Procura (sem criar) a categoria do caminho dado; None se não existir."""
        with self.banco.conectar() as c:
            atual = None
            for nome in nomes:
                atual = self._filho(c, atual, nome)
                if atual is None:
                    return None
            return atual

    # =====================================================================
    # Tags
    # =====================================================================
    @staticmethod
    def _garantir_tag(c: sqlite3.Connection, nome: str) -> int:
        r = c.execute("SELECT id FROM tags WHERE nome=? COLLATE NOCASE", (nome,)).fetchone()
        if r:
            return r[0]
        return c.execute("INSERT INTO tags (nome) VALUES (?)", (nome,)).lastrowid

    def tags(self) -> list[Tag]:
        with self.banco.conectar() as c:
            return [
                Tag(r[0], r[1], r[2])
                for r in c.execute(
                    "SELECT t.id, t.nome, count(qt.questao_id) FROM tags t"
                    " LEFT JOIN questao_tags qt ON qt.tag_id=t.id GROUP BY t.id"
                    " ORDER BY t.nome COLLATE NOCASE"
                )
            ]

    def nomes_tags(self) -> list[str]:
        return [t.nome for t in self.tags()]

    def renomear_tag(self, tid: int, nome: str) -> None:
        nome = nome.strip()
        if not nome:
            raise ErroBanco("O nome da tag não pode ficar vazio.")
        with self.banco.conectar(escrita=True) as c:
            r = c.execute("SELECT id FROM tags WHERE nome=? COLLATE NOCASE", (nome,)).fetchone()
            if r and r[0] != tid:
                raise ErroBanco(f"Já existe a tag “{nome}”. Use “Mesclar”.")
            c.execute("UPDATE tags SET nome=? WHERE id=?", (nome, tid))

    def mesclar_tags(self, origens: Iterable[int], destino: int) -> None:
        with self.banco.conectar(escrita=True) as c:
            for tid in origens:
                if tid == destino:
                    continue
                c.execute(
                    "INSERT OR IGNORE INTO questao_tags (questao_id, tag_id)"
                    " SELECT questao_id, ? FROM questao_tags WHERE tag_id=?",
                    (destino, tid),
                )
                c.execute("DELETE FROM tags WHERE id=?", (tid,))

    def excluir_tag(self, tid: int) -> None:
        with self.banco.conectar(escrita=True) as c:
            c.execute("DELETE FROM tags WHERE id=?", (tid,))

    # =====================================================================
    # Montagens de prova
    # =====================================================================
    def listar_montagens(self) -> list[tuple[int, str, str]]:
        with self.banco.conectar() as c:
            return [
                (r[0], r[1], r[2])
                for r in c.execute("SELECT id, nome, alterada_em FROM montagens ORDER BY alterada_em DESC")
            ]

    def obter_montagem(self, mid: int) -> tuple[str, dict] | None:
        with self.banco.conectar() as c:
            r = c.execute("SELECT nome, dados FROM montagens WHERE id=?", (mid,)).fetchone()
        if r is None:
            return None
        return r[0], json.loads(r[1])

    def salvar_montagem(self, nome: str, dados: dict, mid: int | None = None) -> int:
        agora = agora_iso()
        texto = json.dumps(dados, ensure_ascii=False)
        with self.banco.conectar(escrita=True) as c:
            if mid is not None and c.execute("SELECT 1 FROM montagens WHERE id=?", (mid,)).fetchone():
                c.execute(
                    "UPDATE montagens SET nome=?, dados=?, alterada_em=? WHERE id=?",
                    (nome, texto, agora, mid),
                )
                return mid
            return c.execute(
                "INSERT INTO montagens (nome, dados, criada_em, alterada_em) VALUES (?,?,?,?)",
                (nome, texto, agora, agora),
            ).lastrowid

    def excluir_montagem(self, mid: int) -> None:
        with self.banco.conectar(escrita=True) as c:
            c.execute("DELETE FROM montagens WHERE id=?", (mid,))
