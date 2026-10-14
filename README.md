# Banco de Questões de Matemática

Aplicativo de desktop, em português e 100% offline, para cadastrar questões de
matemática em LaTeX, organizá-las num banco de dados próprio e montar provas em
LaTeX e PDF, com versões embaralhadas, gabarito e resolução.

- Funciona sem internet. O MathJax e todos os outros recursos vêm dentro do
  aplicativo, e a prévia bloqueia qualquer acesso à rede.
- É distribuído como executável para Linux (AppImage ou pasta portátil) e
  Windows (pasta portátil com `.exe`). Não é preciso instalar Python.
- O banco começa vazio, e nada é gravado sem você apertar um botão de salvar.

Veja também: [`PLANO.md`](PLANO.md) (estrutura, esquema do banco e etapas) e
[`DECISOES.md`](DECISOES.md) (decisões tomadas onde o pedido não especificava).

---

## Sumário

1. [Instalar e abrir o aplicativo](#1-instalar-e-abrir-o-aplicativo)
2. [Instalar o TeX](#2-instalar-o-tex)
3. [Onde ficam os dados e como fazer backup](#3-onde-ficam-os-dados-e-como-fazer-backup)
4. [Como usar](#4-como-usar)
5. [Modelos de prova](#5-modelos-de-prova)
6. [Rodar em modo de desenvolvimento](#6-rodar-em-modo-de-desenvolvimento)
7. [Gerar os executáveis](#7-gerar-os-executáveis)
8. [Solução de problemas](#8-solução-de-problemas)
9. [Licenças de terceiros](#9-licenças-de-terceiros)

---

## 1. Instalar e abrir o aplicativo

### Linux (Mint, Ubuntu…)

**AppImage** (um arquivo só):

```bash
chmod +x BancoQuestoes-1.0.0-x86_64.AppImage
./BancoQuestoes-1.0.0-x86_64.AppImage
```

**Pasta portátil** (`.tar.gz`):

```bash
tar -xzf BancoQuestoes-1.0.0-linux-x86_64.tar.gz -C ~/Aplicativos
~/Aplicativos/BancoQuestoes/BancoQuestoes
```

Para criar um atalho no menu, use o arquivo
`empacotamento/appimage/bancoquestoes.desktop` como modelo, ajustando o
caminho em `Exec=`.

### Windows

1. Descompacte `BancoQuestoes-1.0.0-windows-x64.zip` numa pasta, por exemplo
   `C:\Programas\BancoQuestoes`.
2. Abra `BancoQuestoes.exe`. Se quiser, crie um atalho na área de trabalho:
   botão direito no `.exe` > *Enviar para* > *Área de trabalho*.

O Windows SmartScreen pode avisar que o aplicativo "não é reconhecido", porque o
executável não é assinado digitalmente. Clique em *Mais informações* >
*Executar assim mesmo*.

### Primeira abertura

O aplicativo pergunta onde fica o banco:

- **Criar novo banco…**: escolha (ou crie) uma pasta **dentro da pasta
  sincronizada com o Google Drive**, por exemplo
  `~/GoogleDrive/BancoQuestoes` no Linux ou
  `G:\Meu Drive\BancoQuestoes` no Windows.
- **Abrir banco existente…**: escolha a pasta de um banco já criado, por
  exemplo o mesmo banco no outro computador.

Nas próximas vezes, o último banco abre direto. Para trocar de banco, use
*Arquivo > Abrir outro banco…*.

### Autoteste

Para conferir se o executável funciona neste computador, rode
`BancoQuestoes --autoteste` (no Windows,
`BancoQuestoes.exe --autoteste --relatorio resultado.txt`). Ele testa o banco
SQLite, o MathJax na prévia, o PyMuPDF e, se houver TeX, gera um PDF de teste,
tudo numa pasta temporária.

---

## 2. Instalar o TeX

O TeX é necessário para a **prévia exata**, a **checagem de LaTeX ao salvar** e
a **geração de PDF**. Sem ele o aplicativo continua funcionando: a prévia exata
e o PDF ficam desativados, com um aviso, e a exportação gera só os arquivos
`.tex`.

### Linux Mint / Ubuntu: TeX Live

Instalação recomendada (cerca de 600 MB), com português, `enumitem`,
`longtable` e as fontes usadas pelo modelo:

```bash
sudo apt update
sudo apt install texlive-latex-base texlive-latex-recommended texlive-latex-extra \
                 texlive-lang-portuguese texlive-fonts-recommended latexmk
```

Se você usa muitos pacotes (TikZ, pgfplots etc.), instale tudo de uma vez
(cerca de 6 GB):

```bash
sudo apt install texlive-full
```

### Windows: MiKTeX (mais simples) ou TeX Live

- **MiKTeX:** baixe o instalador em <https://miktex.org/download> e instale
  "só para mim" (*just for me*). No **MiKTeX Console**, em *Settings*, coloque
  *"Install missing packages on-the-fly"* em **Always**. Assim a compilação não
  para esperando uma janela de confirmação. Depois clique em *Updates* > *Check
  for updates*.
- **TeX Live:** baixe `install-tl-windows.exe` em
  <https://tug.org/texlive/windows.html> e instale o esquema completo. A
  instalação é maior e mais demorada, mas não precisa baixar pacotes depois.

### Onde o aplicativo procura o TeX

Ele procura o `pdflatex` (ou o `latexmk`) no `PATH` e nos locais usuais de
instalação (`/usr/bin`, `/usr/local/texlive/…`, `%LOCALAPPDATA%\Programs\MiKTeX`,
`C:\Program Files\MiKTeX`, `C:\texlive\20xx\bin\windows`). Se não encontrar,
indique o caminho em **Ferramentas > Configurações > LaTeX**, por exemplo
`C:\Users\voce\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe`, e
clique em **Detectar**. A barra de status mostra se o TeX foi encontrado.

Por segurança, a compilação **nunca** usa `--shell-escape`. Ela sempre usa
`-interaction=nonstopmode` e `-halt-on-error` e tem tempo limite (configurável).

---

## 3. Onde ficam os dados e como fazer backup

### A pasta do banco (sincronizada)

Tudo o que pertence ao banco fica na pasta que você escolheu:

```
BancoQuestoes/
├── banco.sqlite3        questões, categorias, tags, montagens salvas
├── configuracoes.json   preâmbulo/macros, modelo padrão, limites, nº de backups
├── midia/               imagens (nome = hash do conteúdo, ex.: 3f9a1c2b7d4e8f01.png)
├── modelos/             modelos de prova (.tex)
├── backups/             backups automáticos (.zip)
└── banco.trava          existe só enquanto o banco está aberto
```

O SQLite usa o modo de diário `DELETE` (sem WAL), e o aplicativo abre e fecha a
conexão a cada operação. Assim, fora dos instantes de gravação, a pasta só tem os
arquivos acima, o que é ideal para Google Drive e rclone.

### Configurações deste computador (fora da pasta sincronizada)

- Linux: `~/.config/BancoQuestoes/config.json`
- Windows: `%APPDATA%\BancoQuestoes\config.json`

Ficam aí o caminho do TeX, os tempos limite, o último banco aberto, a última
pasta de exportação e o tamanho da janela.

### Usar em mais de um computador (Google Drive / rclone)

O banco foi pensado para ser usado em vários computadores, **um de cada vez**:

1. **Antes de abrir** o aplicativo num computador, garanta que a sincronização
   terminou. Com o rclone, rode a sincronização à mão se ela for periódica.
2. **Ao terminar**, feche o aplicativo e deixe a sincronização enviar os
   arquivos antes de abrir no outro computador.
3. Ao abrir, o aplicativo grava `banco.trava` com o nome do computador e o
   horário. Se encontrar a trava de **outro** computador, ele avisa e deixa
   escolher entre **abrir só para leitura** (seguro) e **abrir assim mesmo**
   (use quando tiver certeza de que o outro computador já fechou e sincronizou;
   por exemplo, se ele travou). A trava é removida quando você fecha o app.

Com o rclone no Linux, prefira o `rclone bisync`, que sincroniza nos dois
sentidos. Não use `rclone sync` de um lado só por cima de uma pasta que também é
alterada no outro computador.

### Backups

- **Automático:** sempre que o banco é aberto, o aplicativo cria em
  `backups/` um `.zip` com o banco, a mídia, os modelos e as configurações.
  Ficam guardados os **últimos 10**; mude esse número em *Ferramentas >
  Configurações > Banco*.
- **Manual e restauração:** em *Arquivo > Backups…* é possível fazer um backup
  agora ou restaurar qualquer um da lista. Antes de restaurar, o aplicativo
  guarda o estado atual num backup `…-antes-de-restaurar.zip`.
- **Exportar/importar o banco inteiro:** *Arquivo > Exportar banco inteiro
  (.zip)…* gera um `.zip` com tudo, que você pode guardar num pendrive ou em
  outro lugar. *Arquivo > Importar banco inteiro (.zip)…* recria o banco numa
  pasta nova.
- Os backups ficam dentro da pasta sincronizada, então também vão para o Google
  Drive. Como cópia extra, de vez em quando use *Exportar banco inteiro* e
  guarde o `.zip` fora do Drive.

---

## 4. Como usar

### Cadastro (aba inicial)

- Escolha o **tipo**: discursiva, múltipla escolha, verdadeiro ou falso ou
  resposta curta. Os campos mudam conforme o tipo.
- Escreva o **enunciado**, as **alternativas** (com a correta marcada e um
  comentário opcional), a **resolução** e as **observações** (que nunca vão
  para a prova), todos em LaTeX.
- **Imagens** (PNG, JPG ou PDF): use o botão *Inserir imagem…*, arraste o
  arquivo para o campo ou cole com Ctrl+V. No texto aparece um marcador como
  `[[img:3f9a1c2b7d4e8f01|0.6]]`, em que `0.6` é a largura (60% da linha).
  Edite o número no texto ou clique com o botão direito no marcador > *Largura
  desta imagem…*.
- **Categoria:** é escolhida numa árvore (ex.: Cálculo > Integrais >
  Substituição). Dá para criar categorias ali mesmo; elas só são gravadas
  quando a questão for salva.
- **Tags:** separadas por vírgula, com autocompletar.
- **Prévia rápida:** atualiza enquanto você digita, usando o MathJax. O que o
  MathJax não mostra (TikZ, por exemplo) aparece como "[use a prévia exata]".
- **Prévia exata:** compila a questão com `pdflatex`, usando seu preâmbulo, e
  mostra o resultado como no PDF.
- **Salvar no banco** (Ctrl+S) ou **Salvar e nova** (mantém tipo, categoria,
  tags, fonte e ano). Ao salvar, o aplicativo:
  1. compila os campos para checar o LaTeX. Se houver erro, mostra a mensagem
     de forma legível e o campo com problema, e você escolhe entre *Corrigir* e
     *Salvar mesmo assim*;
  2. procura questões com enunciado parecido (acima de 85%) e as mostra lado a
     lado, para você decidir se salva.

### Banco

Filtros combináveis (categoria com ou sem subcategorias, tags exigindo todas ou
qualquer uma, tipo, dificuldade, fonte, ano e busca no texto, sem diferenciar
acentos), prévia da questão selecionada, e os botões **Editar**, **Duplicar**
(abre uma cópia não salva no cadastro) e **Excluir** (pede confirmação). Os
botões **Categorias…** e **Tags…** servem para renomear, mover, mesclar e
excluir.

### Montagem de prova

1. **Questões:** marque questões na lista filtrada e clique em *Adicionar
   marcadas à prova*. Também dá para usar a aba **Sorteio por regras** ("N
   questões de [categoria] com [tags], dificuldade [faixa], tipo [x]"). As duas
   formas podem ser combinadas na mesma prova.
2. Na aba **Questões da prova**: arraste para reordenar, remova, **ressorteie**
   uma questão sorteada, e dê duplo clique em *Valor* ou *Espaço (cm)* para
   editar.
3. **Cabeçalho:** título, disciplina, turma, professor, data, instruções e
   modelo de prova.
4. **Versões e exportação:** número de versões (A, B, C…), embaralhar questões,
   embaralhar alternativas (respeitando o "não embaralhar" de cada questão) e a
   **semente**. Com a mesma semente sai exatamente a mesma prova.
5. **Exportar prova…:** escolha a pasta de saída. São gerados, para cada versão,
   `prova_A.tex/.pdf` e `resolucao_A.tex/.pdf` (resolução e comentários de cada
   alternativa), um `gabarito.tex/.pdf` com a tabela de respostas de cada versão
   (letra correta já embaralhada, V/F e resposta curta), a pasta `midia/` com
   as imagens (caminhos relativos: a pasta compila sozinha em outro computador)
   e um `montagem.json` com a semente e a ordem das questões. No fim, o botão
   *Abrir pasta* abre a pasta de saída.
6. **Salvar montagem** guarda tudo no banco, para reabrir depois com *Abrir…*.

### Importação de provas antigas (.tex)

*Arquivo > Importar prova em LaTeX* ou aba **Importação**. O aplicativo
reconhece:

- a classe **exam**: `\question`, `\choice`, `\CorrectChoice`, `solution`,
  `\fillin`, `parts`;
- **enumerate** com `\item`, com as alternativas numa lista aninhada no fim do
  item;
- títulos **"Questão 1"**, **"Questão 2"**…;
- divisão **manual**: linhas contendo só `%%%` entre as questões.

Tudo passa por uma tela de revisão. Nela você junta ou divide questões (o botão
*Dividir no cursor* divide o enunciado onde está o cursor), ajusta o tipo, as
alternativas e a correta, e aplica categoria, tags, fonte, ano e dificuldade a
várias questões de uma vez. Nada é gravado até você clicar em **Gravar no
banco**. As macros do preâmbulo do arquivo podem ser acrescentadas às suas com
um clique.

Para ensinar o importador a reconhecer um formato novo, crie um módulo em
`bancoq/nucleo/importador/` com uma classe derivada de `PadraoImportacao`,
decorada com `@registrar`, e importe-o em `__init__.py`. O arquivo `base.py`
explica como.

### Macros próprias

Em *Ferramentas > Configurações > Preâmbulo e macros*, escreva seus pacotes e
macros (`\usepackage{…}`, `\newcommand{\R}{\mathbb{R}}`,
`\DeclareMathOperator{\sen}{sen}`…). Eles valem na prévia exata, na checagem e
na exportação. As macros `\newcommand`, `\renewcommand`, `\DeclareMathOperator`
e `\def` também são passadas ao MathJax da prévia rápida. O botão *Testar
compilação* confere o preâmbulo.

---

## 5. Modelos de prova

Um modelo é um `.tex` comum com marcadores que o aplicativo substitui:

| Marcador | Conteúdo |
|---|---|
| `<<titulo>>`, `<<disciplina>>`, `<<turma>>`, `<<professor>>`, `<<data>>` | campos do cabeçalho |
| `<<versao>>` | letra da versão (vazio quando há uma só versão) |
| `<<instrucoes>>` | instruções |
| `<<macros>>` | seu preâmbulo/macros (vai antes de `\begin{document}`) |
| `<<questoes>>` | as questões |

Marcadores dentro de comentários (`% <<titulo>>`) não são substituídos.

O aplicativo escreve as questões com estes ambientes e comandos, que **o modelo
define**. Para mudar a aparência da prova, basta editar o modelo:

```latex
\begin{questao}[2,0]          % valor opcional
  Enunciado…
  \begin{alternativas}
    \alt Primeira alternativa
    \alt Segunda alternativa
  \end{alternativas}
  \espacoresposta{5cm}        % discursivas com espaço definido
\end{questao}

\begin{questao}
  Julgue:
  \begin{afirmativas}
    \afirmativa Primeira afirmativa
  \end{afirmativas}
\end{questao}

\begin{questao}
  Quanto vale…?
  \respostacurta              % linha para a resposta curta
\end{questao}
```

O modelo genérico incluído (`modelos/generico.tex` de cada banco) mostra como
definir cada um. Os documentos de resolução e de gabarito usam o preâmbulo do
mesmo modelo, mais os comandos `\marcacorreta`, `\marcavf`, `\comentario`,
`\respostaesperada`, `\respostaalternativa` e o ambiente `resolucao`. Como eles
são definidos com `\providecommand`, você pode redefini-los nas macros ou no
modelo.

Em *Configurações > Modelos de prova* é possível criar (a partir do genérico),
editar, **importar** um `.tex`, duplicar, excluir e escolher o modelo padrão.

---

## 6. Rodar em modo de desenvolvimento

É preciso Python 3.11 ou mais novo.

```bash
git clone <repositório> banco-questoes
cd banco-questoes
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python executar.py                   # ou: python -m bancoq
python executar.py --banco /caminho/do/banco
```

No Linux, o Qt precisa de algumas bibliotecas do sistema, que no Mint/Ubuntu
costumam já estar instaladas. Se faltar alguma (erro do plugin "xcb"), instale:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1
```

### Testes

```bash
python -m pytest -q
```

Os testes cobrem o banco de dados, os filtros e a busca, o embaralhamento e o
gabarito (a resposta correta é conferida em todas as versões), a geração do
`.tex`, o importador, a trava, os backups e as duplicadas. Também há uma
compilação de ponta a ponta com `pdflatex`, que é pulada se o TeX não estiver
instalado. Os dados fictícios usados nos testes ficam só em `tests/`.

### Organização do código

```
bancoq/nucleo/      lógica sem interface (banco, LaTeX, prova, exportação, importador…)
bancoq/interface/   telas em PySide6
bancoq/recursos/    MathJax, página da prévia, modelo genérico, ícone
tests/              pytest e dados fictícios
empacotamento/      spec do PyInstaller e scripts de build
```

---

## 7. Gerar os executáveis

O PyInstaller não gera o executável de um sistema estando no outro: gere o de
Linux no Linux e o de Windows no Windows. Os scripts criam um ambiente virtual
próprio (`.venv-build`), instalam as dependências, rodam os testes e chamam o
PyInstaller.

### Linux

```bash
./empacotamento/build_linux.sh
```

Resultados em `empacotamento/saida/`:

- `dist/BancoQuestoes/BancoQuestoes`: a pasta portátil;
- `BancoQuestoes-<versão>-linux-x86_64.tar.gz`: a pasta compactada;
- `BancoQuestoes-<versão>-x86_64.AppImage`: gerada com o `appimagetool`, que o
  script baixa na primeira vez (precisa de internet só nesse momento).

Variáveis opcionais: `PYTHON=python3.12`, `VENV=/caminho/venv`, `SEM_TESTES=1`,
`SEM_APPIMAGE=1`.

O executável roda em distribuições com a glibc igual ou mais nova que a da
máquina onde foi gerado. Para máxima compatibilidade, gere numa distribuição
mais antiga (o workflow do GitHub usa Ubuntu 22.04).

### Windows

Instale o Python 3.11+ de <https://www.python.org/downloads/>, marcando *"Add
python.exe to PATH"*. Depois, no Prompt de Comando:

```bat
empacotamento\build_windows.bat
```

Resultados em `empacotamento\saida\`: `dist\BancoQuestoes\BancoQuestoes.exe`
(a pasta portátil) e `BancoQuestoes-<versão>-windows-x64.zip`.

### GitHub Actions (gera os executáveis sem precisar de Linux e Windows)

O workflow `.github/workflows/build.yml` gera os dois executáveis num servidor do
GitHub e roda o autoteste em cada um:

- **Publicar uma versão:** crie uma tag começando com `v` (por exemplo,
  `git tag v1.0.1 && git push origin v1.0.1`, ou pela página *Releases > Draft a
  new release* do GitHub). No fim, a página **Releases** do repositório mostra o
  `.AppImage`, o `.tar.gz` (Linux) e o `.zip` (Windows) para baixar. Só entram os
  executáveis que passaram no autoteste.
- **Só testar o build:** na aba *Actions*, escolha *Build* > *Run workflow*. Os
  arquivos ficam em *Artifacts*, na página da execução (por 90 dias).

O GitHub não executa o aplicativo: ele é um programa de desktop. Você baixa o
executável da Release e abre no seu computador.

---

## 8. Solução de problemas

- **A prévia fica em branco no Linux:** rode pelo terminal para ver as mensagens.
  Em algumas máquinas ajuda desligar a aceleração de vídeo do QtWebEngine:
  `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu" ./BancoQuestoes`.
- **"Could not load the Qt platform plugin xcb":** instale `libxcb-cursor0`
  (veja a seção 6).
- **A AppImage não abre ("FUSE"):** instale `libfuse2`
  (`sudo apt install libfuse2`) ou rode
  `./BancoQuestoes-…AppImage --appimage-extract-and-run`. A pasta portátil
  (`.tar.gz`) não precisa de FUSE.
- **MiKTeX abre janelas pedindo para instalar pacotes**, ou a compilação estoura
  o tempo limite: no MiKTeX Console, em *Settings*, coloque *Install missing
  packages* em *Always*. Depois compile uma vez para os pacotes serem baixados.
- **"Option clash for package…"** ao compilar: o pacote foi carregado no modelo
  e de novo, com outras opções, nas suas macros. Deixe-o num lugar só.
- **Erro de LaTeX que só aparece na prova exportada:** abra o `.log` que fica
  na pasta de saída (o nome aparece no relatório da exportação).

---

## 9. Licenças de terceiros

- **MathJax 3.2.2:** Apache License 2.0 (`bancoq/recursos/mathjax/LICENSE`).
- **Qt / PySide6:** LGPL v3.
- **PyMuPDF:** AGPL v3 (uso pessoal; se for redistribuir o executável, veja os
  termos da AGPL).
- **rapidfuzz:** MIT.
- **PyInstaller:** GPL com exceção para os executáveis gerados.
