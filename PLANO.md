# Plano de implementação — Banco de Questões de Matemática

Este documento foi escrito antes do código. As decisões que não estavam
especificadas estão em [`DECISOES.md`](DECISOES.md).

## 1. Estrutura de pastas do projeto

```
banco-questoes/
├── README.md                 instruções em português (rodar, gerar executáveis, TeX, dados)
├── PLANO.md                  este arquivo
├── DECISOES.md               decisões tomadas onde o pedido não especificava
├── requirements.txt          dependências de execução
├── requirements-dev.txt      + pytest e pyinstaller
├── executar.py               ponto de entrada em modo de desenvolvimento
├── bancoq/                   pacote principal
│   ├── __main__.py           permite `python -m bancoq`
│   ├── app.py                cria a QApplication, abre o banco e a janela principal
│   ├── caminhos.py           recursos empacotados (dev x PyInstaller) e pasta de config local
│   ├── config_local.py       configurações da máquina (JSON fora da pasta sincronizada)
│   ├── nucleo/               lógica sem interface gráfica (testável com pytest)
│   │   ├── entidades.py      dataclasses: Questao, Item, Categoria, ...
│   │   ├── banco.py          conexão SQLite curta, esquema, migrações
│   │   ├── repositorio.py    CRUD de questões, categorias, tags, montagens; filtros e FTS5
│   │   ├── midia.py          imagens: hash, cópia para midia/, marcadores [[img:ID|largura]]
│   │   ├── config_banco.py   configurações que pertencem ao banco (JSON dentro da pasta)
│   │   ├── latex_html.py     conversão do subconjunto de LaTeX para HTML (prévia rápida)
│   │   ├── macros.py         leitura de \newcommand etc. para o MathJax
│   │   ├── latex_gerar.py    geração do LaTeX das questões, provas, gabaritos e resoluções
│   │   ├── compilador.py     localizar pdflatex/latexmk, compilar com tempo limite, ler o log
│   │   ├── checagem.py       checagem de LaTeX campo a campo ao salvar
│   │   ├── modelos_prova.py  modelos .tex com marcadores <<...>>
│   │   ├── prova.py          montagem, regras de sorteio, versões, semente, gabarito
│   │   ├── exportar.py       exportação da pasta final (.tex, PDF, gabaritos, mídia)
│   │   ├── duplicadas.py     normalização do enunciado e comparação com rapidfuzz
│   │   ├── trava.py          arquivo de trava do banco
│   │   ├── backup.py         backups .zip automáticos, restauração, exportar/importar banco
│   │   └── importador/       importação de .tex (um módulo por padrão, com registro)
│   │       ├── base.py       interface PadraoImportacao + registro + utilidades
│   │       ├── exam.py       classe exam (\question, \choice, \CorrectChoice, solution)
│   │       ├── enumerate.py  enumerate/\item aninhados
│   │       └── manual.py     divisão manual por separador
│   ├── interface/            telas PySide6
│   │   ├── janela_principal.py
│   │   ├── cadastro.py       tela de cadastro (aba inicial)
│   │   ├── editor_latex.py   editor com destaque de sintaxe, arrastar/colar imagens
│   │   ├── itens.py          editor de alternativas/afirmativas
│   │   ├── previa.py         QWebEngineView + MathJax local; prévia exata (PyMuPDF)
│   │   ├── categorias.py     seletor em árvore e gerenciador de categorias
│   │   ├── tags.py           campo de tags com autocompletar e gerenciador de tags
│   │   ├── filtros.py        painel de filtros reutilizado no banco e na montagem
│   │   ├── banco_tela.py     tela do banco
│   │   ├── montagem.py       montagem de prova, sorteio, versões e exportação
│   │   ├── importacao.py     tela de revisão da importação
│   │   ├── configuracoes.py  macros, modelos, TeX, limites, backups
│   │   ├── dialogos.py       erro de LaTeX, duplicada lado a lado, abrir banco, trava
│   │   └── tarefas.py        execução em segundo plano (QThread)
│   └── recursos/
│       ├── previa.html       página da prévia rápida
│       ├── mathjax/          MathJax 3.2.2 (tex-svg-full.js + LICENSE), sem CDN
│       ├── modelos/generico.tex, gabarito.tex, resolucao.tex
│       └── icone.png / icone.svg
├── tests/                    pytest; dados fictícios só aqui
│   ├── dados/                .tex de exemplo para o importador
│   └── test_*.py
├── empacotamento/
│   ├── bancoq.spec           especificação do PyInstaller
│   ├── build_linux.sh        pasta portátil .tar.gz e AppImage
│   ├── build_windows.bat     pasta portátil com .exe (.zip)
│   └── appimage/             AppRun, .desktop
└── .github/workflows/build.yml   gera Linux e Windows no GitHub Actions
```

## 2. Pasta de um banco (sincronizada)

```
MeuBanco/                     pasta escolhida pelo usuário (Google Drive / rclone)
├── banco.sqlite3             SQLite, journal_mode=DELETE, conexões curtas
├── configuracoes.json        preâmbulo/macros, modelo padrão, limite de duplicadas, nº de backups
├── midia/                    imagens com nome = hash do conteúdo (ex.: 3f9a1c2b7d4e8f01.png)
├── modelos/                  modelos de prova .tex (o genérico é copiado na criação)
├── backups/                  backup-AAAAMMDD-HHMMSS-computador.zip (últimos N)
└── banco.trava               existe só enquanto o banco está aberto
```

Configuração da máquina (fora da pasta sincronizada):
`~/.config/BancoQuestoes/config.json` (Linux) ou `%APPDATA%\BancoQuestoes\config.json` (Windows):
último banco aberto, caminho do pdflatex/latexmk, tempo limite, tamanho das janelas.

## 3. Esquema do banco (SQLite)

```sql
PRAGMA user_version = 1;           -- versão do esquema

CREATE TABLE categorias (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL,
    pai_id  INTEGER REFERENCES categorias(id) ON DELETE CASCADE
);

CREATE TABLE tags (
    id      INTEGER PRIMARY KEY,
    nome    TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE questoes (
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
    criada_em       TEXT NOT NULL,     -- ISO 8601, horário local
    alterada_em     TEXT NOT NULL
);

-- alternativas (múltipla escolha) e afirmativas (V/F)
CREATE TABLE itens (
    id          INTEGER PRIMARY KEY,
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL,
    texto       TEXT NOT NULL DEFAULT '',
    correta     INTEGER NOT NULL DEFAULT 0,   -- múltipla: correta; V/F: 1 = V, 0 = F
    comentario  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE questao_tags (
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (questao_id, tag_id)
);

-- cada imagem fica ligada à questão (item_id NULL) ou a uma alternativa
CREATE TABLE imagens (
    id          INTEGER PRIMARY KEY,
    questao_id  INTEGER NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
    item_id     INTEGER REFERENCES itens(id) ON DELETE CASCADE,
    arquivo     TEXT NOT NULL                 -- nome em midia/, ex.: 3f9a1c2b7d4e8f01.png
);

-- montagens de prova salvas (cabeçalho, questões, regras, versões, semente) em JSON
CREATE TABLE montagens (
    id           INTEGER PRIMARY KEY,
    nome         TEXT NOT NULL,
    dados        TEXT NOT NULL,
    criada_em    TEXT NOT NULL,
    alterada_em  TEXT NOT NULL
);

-- busca textual (rowid = questoes.id), sem acentos
CREATE VIRTUAL TABLE questoes_fts USING fts5(
    enunciado, alternativas, resolucao, observacoes,
    tokenize = 'unicode61 remove_diacritics 2'
);
```

## 4. Etapas (um commit por etapa; o app fica utilizável ao fim de cada uma)

1. **Cadastro, banco e prévia rápida** — criar/abrir banco, esquema, tela de cadastro
   com tipos, alternativas/afirmativas, imagens (arquivo, arrastar, colar), categoria em
   árvore, tags com autocompletar, salvar/salvar e nova/limpar, Ctrl+S, aviso de
   alterações não salvas, prévia MathJax local com atraso de 0,5 s.
2. **Filtros, busca e gerenciamento** — tela do banco com filtros combináveis e FTS5,
   prévia, editar/duplicar/excluir, gerenciar categorias e tags (renomear, mesclar, excluir).
3. **Macros, prévia exata e checagem ao salvar** — Configurações (preâmbulo/macros,
   caminho do TeX), macros no MathJax, prévia exata com pdflatex em segundo plano,
   checagem campo a campo com log legível.
4. **Montagem, versões e exportação** — seleção manual e por regras, ressorteio,
   reordenar, valores, espaço de resposta, cabeçalho, versões com semente, modelos de
   prova, exportação (.tex, PDF, gabarito, resolução, mídia), montagens salvas.
5. **Importação de .tex** — padrões `exam` e `enumerate`, divisão manual, tela de revisão.
6. **Trava, backups e duplicadas** — arquivo de trava, backup automático/restauração,
   exportar/importar banco .zip, detecção de duplicadas lado a lado.
7. **Empacotamento** — PyInstaller (Linux e Windows), AppImage, workflow do GitHub Actions,
   README, teste do executável Linux.

## 5. Testes (pytest)

- `test_banco.py`: esquema, CRUD, categorias (árvore, mesclar), tags, filtros, FTS5, imagens.
- `test_prova.py`: sorteio por regras, versões, semente reprodutível, gabarito correto em todas as versões.
- `test_latex.py`: prévia HTML, macros, geração do .tex da prova, cópia de mídia.
- `test_importador.py`: exam, enumerate aninhado, divisão manual.
- `test_compilacao.py`: ponta a ponta com pdflatex (pulado se não houver TeX).
- `test_trava_backup.py`, `test_duplicadas.py`.
