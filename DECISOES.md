# Decisões tomadas

Onde o pedido não especificava algo, escolhi a opção mais simples. Cada decisão
está registrada aqui, por etapa.

## Tecnologia

- **Python 3.11+ com PySide6, QWebEngineView, SQLite/FTS5, PyMuPDF, rapidfuzz e
  PyInstaller**, como sugerido. Nenhuma troca foi necessária. O desenvolvimento e
  os testes foram feitos com Python 3.13 e PySide6 6.12; o código evita recursos
  posteriores ao Python 3.11.
- **MathJax 3.2.2, componente `tex-svg-full.js`.** É um único arquivo que já traz
  todas as extensões do TeX e as fontes (saída em SVG). Assim não há carregamento
  sob demanda de outros arquivos, nem de CDN. O arquivo foi conferido com o
  checksum publicado no registro npm e está em `bancoq/recursos/mathjax/`, junto
  com a licença (Apache 2.0).
- **Bloqueio de rede na prévia.** O perfil do QtWebEngine é "off-the-record" (não
  grava cache nem cookies em disco) e tem um interceptador que bloqueia qualquer
  URL que não seja `file:`, `data:`, `qrc:`, `about:` ou `blob:`. Cliques em links
  são ignorados. O Chromium também recebe flags que desligam rede em segundo plano.
- **Sandbox do Chromium.** No executável Linux (e quando o app roda como root) a
  variável `QTWEBENGINE_DISABLE_SANDBOX=1` é definida. Em AppImages o sandbox
  costuma falhar ("No usable sandbox"), principalmente em sistemas baseados no
  Ubuntu 24.04. Como a prévia só mostra conteúdo local e a rede está bloqueada,
  o risco é baixo.
- **Tradução do Qt.** Os botões padrão dos diálogos (Sim, Não, Cancelar, Abrir…)
  usam as traduções `qtbase_pt_BR` que vêm com o PySide6.

## Etapa 1: cadastro, banco e prévia rápida

- **Pasta do banco:** `banco.sqlite3`, `configuracoes.json`, `midia/`, `modelos/`
  e `backups/`, todos dentro da pasta sincronizada.
- **Configurações do banco** (preâmbulo/macros, modelo padrão, limite de
  duplicadas, número de backups, checagens ao salvar) ficam em
  `configuracoes.json`, um JSON legível. As da máquina (caminho do TeX, último
  banco, tamanho da janela) ficam em `~/.config/BancoQuestoes/config.json`
  (Linux) ou `%APPDATA%\BancoQuestoes\config.json` (Windows).
- **SQLite:** `journal_mode=DELETE` (o padrão, sem WAL) e `synchronous=FULL`.
  Cada operação abre a conexão, faz o trabalho numa transação e fecha. Assim,
  fora das escritas, só existe o arquivo `banco.sqlite3` na pasta.
- **Alternativas e afirmativas** ficam na mesma tabela `itens`. A coluna `correta`
  significa "correta" na múltipla escolha e "verdadeira" no V/F.
- **Dificuldade** é obrigatória, de 1 a 5, com padrão 3. **Ano** é opcional.
- **Questão nova de múltipla escolha** começa com 5 alternativas em branco, e a de
  V/F com 4 afirmativas. Ao salvar, alternativas totalmente vazias (sem texto, sem
  comentário e sem marcação) são descartadas.
- **Validação ao salvar:** enunciado vazio impede o salvamento. Já menos de duas
  alternativas, nenhuma ou mais de uma correta, V/F sem afirmativas e resposta
  curta vazia geram um aviso com a opção "Salvar mesmo assim".
- **Imagens:** o nome do arquivo em `midia/` são os 16 primeiros dígitos
  hexadecimais do SHA-256 do conteúdo (ex.: `3f9a1c2b7d4e8f01.png`). O mesmo
  identificador vai no marcador: `[[img:3f9a1c2b7d4e8f01|0.6]]`, em que o número é
  a largura como fração da linha (também aceita `|60%`). O padrão é 0,6. A largura
  pode ser editada no texto ou pelo menu do botão direito ("Largura desta
  imagem…"). Imagens coladas da área de transferência são gravadas como PNG.
- **"Nada é gravado sem salvar" vale também para imagens e categorias.** Uma imagem
  inserida fica numa pasta temporária e só é copiada para `midia/` ao salvar a
  questão. Uma categoria criada no seletor da tela de cadastro aparece em itálico
  e só é criada no banco junto com a questão.
- **Ligação imagem ↔ questão/alternativa** (tabela `imagens`) é recalculada a cada
  salvamento, a partir dos marcadores presentes no enunciado, na resolução e na
  resposta (ligadas à questão) e em cada alternativa ou comentário (ligadas àquela
  alternativa). Arquivos de `midia/` nunca são apagados automaticamente, porque a
  mesma imagem pode estar em várias questões.
- **"Duplicar" não grava nada:** abre uma cópia não salva na tela de cadastro.
- **Prévia rápida:** a matemática vai para o MathJax com os delimitadores `\( \)` e
  `\[ \]`. O texto em volta é convertido em Python (`nucleo/latex_html.py`). Além
  do pedido (parágrafos, `\textbf`, `\emph`, `itemize`, `enumerate`), o conversor
  entende `tabular` simples, `center`, `\\`, acentos no estilo `\'a` e `\c{c}`, e
  alguns símbolos. Ambientes e comandos desconhecidos viram "[use a prévia
  exata]", e o nome do comando aparece ao passar o mouse.
- **Observações** aparecem na prévia (num quadro "não vão para a prova"), mas nunca
  na prova nem nos gabaritos.
