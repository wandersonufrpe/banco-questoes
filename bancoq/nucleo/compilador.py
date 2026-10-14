"""Localiza o pdflatex/latexmk, compila com tempo limite e interpreta o log.

Segurança: nunca usa ``--shell-escape``; sempre usa ``-interaction=nonstopmode``
e ``-halt-on-error``; desliga explicitamente o shell-escape (``-no-shell-escape``
no TeX Live, ``--disable-write18`` no MiKTeX).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

EXE = ".exe" if sys.platform.startswith("win") else ""


@dataclass
class InfoTex:
    motor: str            # "pdflatex" ou "latexmk"
    caminho: str
    miktex: bool = False
    versao: str = ""

    def descricao(self) -> str:
        return f"{self.motor}: {self.caminho}" + (f" ({self.versao})" if self.versao else "")


@dataclass
class ErroLatex:
    mensagem: str                 # linha "! ..." do log
    linha: int | None = None      # linha do .tex indicada por "l.N"
    trecho: str = ""              # texto perto do erro
    explicacao: str = ""          # explicação em português


@dataclass
class ResultadoCompilacao:
    ok: bool
    pdf: Path | None = None
    log: str = ""
    erro: ErroLatex | None = None
    tempo_esgotado: bool = False
    cancelado: bool = False
    saida: str = ""
    avisos: list[str] = field(default_factory=list)


# =============================================================================
# localizar
# =============================================================================
def _candidatos_padrao() -> list[str]:
    res: list[str] = []
    if sys.platform.startswith("win"):
        locais = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64"),
            os.path.expandvars(r"%ProgramFiles%\MiKTeX\miktex\bin\x64"),
            os.path.expandvars(r"%ProgramFiles(x86)%\MiKTeX\miktex\bin"),
            os.path.expandvars(r"%ProgramFiles%\MiKTeX 2.9\miktex\bin\x64"),
        ]
        for base in ("C:\\texlive", os.path.expandvars(r"%USERPROFILE%\texlive")):
            for ano in sorted(glob.glob(os.path.join(base, "20*")), reverse=True):
                locais += [os.path.join(ano, "bin", s) for s in ("windows", "win64", "win32")]
        res = locais
    elif sys.platform == "darwin":
        res = ["/Library/TeX/texbin", "/usr/local/bin", "/opt/homebrew/bin"]
    else:
        res = ["/usr/bin", "/usr/local/bin"]
        for base in ("/usr/local/texlive", os.path.expanduser("~/texlive")):
            for ano in sorted(glob.glob(os.path.join(base, "20*")), reverse=True):
                res += glob.glob(os.path.join(ano, "bin", "*"))
    return [p for p in res if p and os.path.isdir(p)]


def _info(caminho: str) -> InfoTex:
    nome = Path(caminho).name.lower()
    motor = "latexmk" if nome.startswith("latexmk") else "pdflatex"
    info = InfoTex(motor, caminho)
    try:
        r = subprocess.run(
            [caminho, "--version"], capture_output=True, text=True, timeout=15,
            errors="replace", stdin=subprocess.DEVNULL, **_opcoes_processo(),
        )
        primeira = (r.stdout or r.stderr).strip().splitlines()
        info.versao = primeira[0][:80] if primeira else ""
        info.miktex = "miktex" in (r.stdout + r.stderr).lower()
    except (OSError, subprocess.SubprocessError):
        pass
    if "miktex" in caminho.lower():
        info.miktex = True
    return info


def localizar_tex(configurado: str = "") -> InfoTex | None:
    """Procura no caminho configurado, no PATH e nos lugares usuais de instalação."""
    configurado = (configurado or "").strip().strip('"')
    if configurado:
        p = Path(configurado)
        if p.is_file():
            return _info(str(p))
        if p.is_dir():
            for nome in ("pdflatex", "latexmk"):
                alvo = p / (nome + EXE)
                if alvo.is_file():
                    return _info(str(alvo))
    for nome in ("pdflatex", "latexmk"):
        achado = shutil.which(nome)
        if achado:
            return _info(achado)
    for pasta in _candidatos_padrao():
        for nome in ("pdflatex", "latexmk"):
            alvo = os.path.join(pasta, nome + EXE)
            if os.path.isfile(alvo):
                return _info(alvo)
    return None


# =============================================================================
# compilar
# =============================================================================
def _opcoes_processo() -> dict:
    if sys.platform.startswith("win"):
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {"start_new_session": True}


def comando(info: InfoTex, arquivo: str) -> list[str]:
    seguranca = "--disable-write18" if info.miktex else "-no-shell-escape"
    if info.motor == "latexmk":
        cmd = [info.caminho, "-pdf", "-interaction=nonstopmode", "-halt-on-error"]
        if info.miktex:
            cmd.append("-pdflatex=pdflatex --disable-write18 %O %S")
        else:
            cmd.append("-no-shell-escape")
        return cmd + [arquivo]
    return [info.caminho, "-interaction=nonstopmode", "-halt-on-error", seguranca, arquivo]


class Compilacao:
    """Uma compilação que pode ser cancelada de outra thread."""

    def __init__(self, info: InfoTex, pasta: Path, nome_tex: str, tempo_limite: float = 30,
                 passadas: int = 1):
        self.info = info
        self.pasta = Path(pasta)
        self.nome_tex = nome_tex
        self.tempo_limite = tempo_limite
        self.passadas = 1 if info.motor == "latexmk" else max(1, passadas)
        self._proc: subprocess.Popen | None = None
        self._cancelado = False
        self._trava = threading.Lock()

    def cancelar(self) -> None:
        with self._trava:
            self._cancelado = True
            if self._proc is not None:
                _matar(self._proc)

    def executar(self) -> ResultadoCompilacao:
        env = dict(os.environ)
        env.setdefault("max_print_line", "1000")
        env["openout_any"] = "p"
        env["shell_escape"] = "f"
        base = Path(self.nome_tex).stem
        log_path = self.pasta / f"{base}.log"
        pdf_path = self.pasta / f"{base}.pdf"
        saida = ""
        inicio = time.monotonic()
        for _ in range(self.passadas):
            restante = self.tempo_limite - (time.monotonic() - inicio)
            if restante <= 0:
                return ResultadoCompilacao(False, log=_ler(log_path), tempo_esgotado=True, saida=saida)
            with self._trava:
                if self._cancelado:
                    return ResultadoCompilacao(False, cancelado=True)
                try:
                    self._proc = subprocess.Popen(
                        comando(self.info, self.nome_tex), cwd=self.pasta, env=env,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        **_opcoes_processo(),
                    )
                except OSError as e:
                    return ResultadoCompilacao(False, saida=str(e),
                                               erro=ErroLatex(f"Não foi possível executar {self.info.caminho}: {e}"))
            try:
                bruto, _ = self._proc.communicate(timeout=restante)
                saida = bruto.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                _matar(self._proc)
                self._proc.communicate()
                return ResultadoCompilacao(False, log=_ler(log_path), tempo_esgotado=True, saida=saida)
            if self._cancelado:
                return ResultadoCompilacao(False, cancelado=True)
            codigo = self._proc.returncode
            log = _ler(log_path)
            if codigo != 0 or not pdf_path.exists():
                erro = ler_erro_log(log or saida)
                return ResultadoCompilacao(False, log=log, erro=erro, saida=saida)
            if "Rerun to get" not in log and "rerunfilecheck" not in log and "Label(s) may have changed" not in log:
                break
        log = _ler(log_path)
        return ResultadoCompilacao(True, pdf=pdf_path, log=log, saida=saida, avisos=avisos_log(log))


def _matar(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                           **_opcoes_processo())
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        try:
            proc.kill()
        except OSError:
            pass


def _ler(caminho: Path) -> str:
    try:
        dados = caminho.read_bytes()
    except OSError:
        return ""
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("latin-1")


def compilar(info: InfoTex, pasta: Path, nome_tex: str, tempo_limite: float = 30,
             passadas: int = 1) -> ResultadoCompilacao:
    return Compilacao(info, pasta, nome_tex, tempo_limite, passadas).executar()


# =============================================================================
# log
# =============================================================================
RE_LINHA = re.compile(r"^l\.(\d+) ?(.*)$")


def ler_erro_log(log: str) -> ErroLatex | None:
    linhas = log.splitlines()
    idx = None
    for i, ln in enumerate(linhas):
        if ln.startswith("! ") and "Emergency stop" not in ln:
            idx = i
            break
    if idx is None:
        for i, ln in enumerate(linhas):
            if ln.startswith("!"):
                idx = i
                break
    if idx is None:
        m = re.search(r"^(.*(?:Fatal error|not found|cannot be found).*)$", log, re.M | re.I)
        if m:
            return ErroLatex(m.group(1).strip(), explicacao=explicar(m.group(1)))
        return None
    mensagem = linhas[idx][2:].strip() if linhas[idx].startswith("! ") else linhas[idx][1:].strip()
    # mensagens do LaTeX podem continuar na linha seguinte
    j = idx + 1
    while j < len(linhas) and linhas[j].strip() and not linhas[j].startswith(("l.", "See ", "Type ", "?")) \
            and len(mensagem) < 300 and not RE_LINHA.match(linhas[j]) and linhas[j].startswith(" "):
        mensagem += " " + linhas[j].strip()
        j += 1
    linha_num = None
    trecho = ""
    for k in range(idx + 1, min(idx + 40, len(linhas))):
        m = RE_LINHA.match(linhas[k])
        if m:
            linha_num = int(m.group(1))
            depois = linhas[k + 1].strip() if k + 1 < len(linhas) else ""
            trecho = (m.group(2).rstrip() + " ⟨erro aqui⟩ " + depois).strip()
            break
    if linha_num is None:
        for k in range(max(0, idx - 6), idx):
            if linhas[k].startswith("Runaway argument"):
                trecho = linhas[k + 1].strip() if k + 1 < len(linhas) else ""
                break
    if "Undefined control sequence" in mensagem and linha_num is not None:
        cmd = re.findall(r"(\\[A-Za-z@]+)\s*$", m.group(2) if m else "")
        if cmd:
            mensagem += f" ({cmd[-1]})"
    return ErroLatex(mensagem, linha_num, trecho, explicar(mensagem))


EXPLICACOES = [
    (r"Undefined control sequence", "Comando não definido. Confira a grafia ou defina-o em Configurações > Preâmbulo e macros."),
    (r"Missing \$ inserted", "Falta um $: provavelmente há matemática (^, _, \\frac…) fora do modo matemático, ou um $ não foi fechado."),
    (r"Extra \}, or forgotten \$", "Há uma chave } a mais, ou um $ esquecido."),
    (r"Missing \} inserted", "Falta fechar uma chave }."),
    (r"Missing \{ inserted", "Falta abrir uma chave {."),
    (r"Extra alignment tab", "Há & demais numa linha de tabela/matriz."),
    (r"Misplaced alignment tab", "O caractere & só pode ser usado em tabelas e alinhamentos. Para o símbolo, use \\&."),
    (r"File `([^']+)' not found", "Arquivo ou pacote não encontrado: \\1. Instale o pacote no TeX ou confira o nome."),
    (r"Environment (\S+) undefined", "Ambiente \\1 não definido. Confira o nome ou carregue o pacote que o define."),
    (r"\\begin\{(\S+)\} on input line \d+ ended by \\end\{(\S+)\}", "Ambiente \\1 fechado com \\end{\\2}."),
    (r"Runaway argument", "Argumento sem fim: provavelmente falta fechar uma chave }."),
    (r"Paragraph ended before", "Um comando recebeu um argumento que atravessa uma linha em branco; provavelmente falta fechar uma chave }."),
    (r"File ended while scanning", "O texto terminou antes de fechar uma chave } ou um ambiente."),
    (r"Double superscript", "Dois expoentes seguidos (x^2^3). Use chaves: x^{2^3}."),
    (r"Double subscript", "Dois índices seguidos (x_1_2). Use chaves: x_{1_2}."),
    (r"Display math should end with \$\$", "Matemática destacada $$…$$ mal fechada."),
    (r"Bad math environment delimiter", "Delimitador de matemática mal usado (\\[ \\] ou \\( \\))."),
    (r"Too many \}'s", "Há chaves } demais."),
    (r"Option clash for package (\S+)", "O pacote \\1 foi carregado duas vezes com opções diferentes (no modelo e nas suas macros)."),
    (r"Command (\S+) already defined", "O comando \\1 já existe. Use \\renewcommand em vez de \\newcommand."),
    (r"Lonely \\item", "\\item fora de uma lista (itemize/enumerate)."),
    (r"There's no line here to end", "\\\\ usado onde não há linha para terminar (por exemplo, numa linha em branco)."),
    (r"Illegal unit of measure", "Unidade de medida inválida (use cm, mm, pt, em…)."),
    (r"Cannot determine size of graphic", "Não foi possível ler o tamanho da imagem."),
    (r"Unknown graphics extension", "Formato de imagem não suportado pelo pdflatex."),
    (r"Emergency stop", "A compilação foi interrompida."),
]


def explicar(mensagem: str) -> str:
    for padrao, texto in EXPLICACOES:
        m = re.search(padrao, mensagem)
        if m:
            try:
                return m.expand(texto)
            except (re.error, IndexError):
                return texto
    return ""


def avisos_log(log: str) -> list[str]:
    avisos = []
    for m in re.finditer(r"^(?:LaTeX|Package \w+) Warning: (.+)$", log, re.M):
        if "Rerun" not in m.group(1):
            avisos.append(m.group(1).strip())
    return avisos[:20]
