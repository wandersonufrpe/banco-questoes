"""Arquivo de trava, backups e detecção de duplicadas."""

import json
import zipfile

import pytest

from bancoq.nucleo import trava
from bancoq.nucleo.backup import (
    ErroBackup, criar_backup, escrever_zip, importar_banco_zip, listar_backups, restaurar_backup,
)
from bancoq.nucleo.banco import Banco
from bancoq.nucleo.duplicadas import normalizar, procurar_parecidas
from bancoq.nucleo.entidades import Questao

from conftest import png_minimo


# ---- trava -----------------------------------------------------------------------
def test_trava_criar_ler_remover(banco):
    assert trava.situacao(banco.pasta) == ("livre", None)
    info = trava.criar_trava(banco.pasta)
    assert info.computador == trava.nome_computador()
    lida = trava.ler_trava(banco.pasta)
    assert lida == info
    # trava desta sessão, deste processo: "esquecida" do ponto de vista de outra abertura
    estado, _ = trava.situacao(banco.pasta)
    assert estado == "esquecida"
    assert not trava.remover_trava(banco.pasta, "outra-sessao")
    assert trava.remover_trava(banco.pasta, info.sessao)
    assert trava.ler_trava(banco.pasta) is None


def test_trava_de_outro_computador(banco):
    (banco.pasta / trava.ARQUIVO_TRAVA).write_text(json.dumps(
        {"computador": "notebook-da-casa", "usuario": "prof", "horario": "2026-01-01T10:00:00", "pid": 1, "sessao": "x"}
    ), encoding="utf-8")
    estado, info = trava.situacao(banco.pasta)
    assert estado == "outro_computador" and info.computador == "notebook-da-casa"
    assert info.horario_legivel() == "01/01/2026 às 10:00"
    # nossa remoção não apaga a trava alheia
    assert not trava.remover_trava(banco.pasta, "minha")
    assert (banco.pasta / trava.ARQUIVO_TRAVA).exists()


def test_trava_ilegivel(banco):
    (banco.pasta / trava.ARQUIVO_TRAVA).write_text("{conflito", encoding="utf-8")
    assert trava.situacao(banco.pasta)[0] == "outro_computador"


# ---- backups -----------------------------------------------------------------------
def _povoar(repo):
    ident = repo.midia.adicionar_bytes(png_minimo(1))
    repo.salvar_questao(Questao(enunciado=f"Original [[img:{ident}]]"))
    return ident


def test_backup_contem_banco_midia_modelos(repo, banco):
    ident = _povoar(repo)
    z = criar_backup(banco, manter=10)
    assert z.parent == banco.pasta_backups
    with zipfile.ZipFile(z) as f:
        nomes = set(f.namelist())
    assert {"banco.sqlite3", "configuracoes.json", "modelos/generico.tex", f"midia/{ident}.png"} <= nomes
    assert not any(n.startswith("backups/") or n.endswith(".trava") for n in nomes)


def test_mantem_so_os_ultimos_n(repo, banco):
    for _ in range(5):
        criar_backup(banco, manter=3)
    assert len(listar_backups(banco)) == 3


def test_restaurar_backup(repo, banco):
    _povoar(repo)
    z = criar_backup(banco)
    repo.salvar_questao(Questao(enunciado="Depois do backup"))
    (banco.pasta / "modelos" / "generico.tex").write_text("alterado", encoding="utf-8")
    assert repo.contar_questoes() == 2
    seguranca = restaurar_backup(banco, z)
    assert seguranca.exists() and "antes-de-restaurar" in seguranca.name
    assert repo.contar_questoes() == 1
    assert repo.buscar()[0].enunciado.startswith("Original")
    assert "alterado" not in (banco.pasta / "modelos" / "generico.tex").read_text(encoding="utf-8")
    # o backup de segurança tem as 2 questões
    restaurar_backup(banco, seguranca)
    assert repo.contar_questoes() == 2


def test_exportar_e_importar_banco_zip(repo, banco, tmp_path):
    ident = _povoar(repo)
    z = escrever_zip(banco, tmp_path / "meu-banco.zip")
    novo = importar_banco_zip(z, tmp_path / "copia")
    b2 = Banco(novo)
    with b2.conectar() as c:
        assert c.execute("SELECT count(*) FROM questoes").fetchone()[0] == 1
    assert (novo / "midia" / f"{ident}.png").exists()
    with pytest.raises(ErroBackup):
        importar_banco_zip(z, novo)                  # não sobrescreve banco existente


def test_zip_invalido_e_recusado(banco, tmp_path):
    ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("banco.sqlite3", b"nao e sqlite")
        z.writestr("../fora.txt", "x")
    with pytest.raises(ErroBackup):
        restaurar_backup(banco, ruim)
    with pytest.raises(ErroBackup):
        importar_banco_zip(ruim, tmp_path / "dest")


# ---- duplicadas --------------------------------------------------------------------
def test_normalizar_ignora_espacos_e_formatacao():
    a = normalizar(r"Calcule   \textbf{a integral} $\int_0^1 x^2\,dx$.")
    b = normalizar("calcule a integral\n$\\int_0^1   x^2 dx$.")
    assert a == b


def test_procurar_parecidas(repo):
    ids = [
        repo.salvar_questao(Questao(enunciado=r"Calcule a integral $\int_0^1 x^2\,dx$ usando o Teorema Fundamental.")),
        repo.salvar_questao(Questao(enunciado=r"Determine o núcleo da transformação linear $T(x,y)=(x+y,0)$.")),
        repo.salvar_questao(Questao(enunciado=r"Calcule a integral $\int_0^2 x^3\,dx$ usando o Teorema Fundamental.")),
    ]
    novo = r"\textbf{Calcule} a integral $\int_0^1 x^2 dx$ usando o teorema fundamental."
    achadas = procurar_parecidas(novo, repo.enunciados(), limite=85)
    assert achadas[0][0] == ids[0] and achadas[0][1] == 100
    assert ids[1] not in [i for i, _ in achadas]
    assert procurar_parecidas(novo, repo.enunciados(), limite=85, excluir_id=ids[0])[0][0] == ids[2]
    assert procurar_parecidas(novo, repo.enunciados(), limite=99.5, excluir_id=ids[0]) == []
    assert procurar_parecidas("Calcule.", repo.enunciados()) == []   # curta demais
