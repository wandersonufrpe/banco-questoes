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

## Etapa 2: filtros, busca e gerenciamento

- **Busca textual:** FTS5 com o tokenizador `unicode61 remove_diacritics 2`
  (ignora acentos e maiúsculas). Cada palavra digitada é procurada como prefixo, e
  todas precisam aparecer (E lógico). O índice cobre o enunciado, as
  alternativas/afirmativas e seus comentários, a resposta curta, a resolução e as
  observações. Se o SQLite de alguma máquina não tiver FTS5, a busca passa a usar
  `LIKE` sem acentos. O índice é marcado como desatualizado e reconstruído na
  próxima abertura numa máquina com FTS5.
- **Filtro de fonte:** "contém", sem diferenciar acentos e maiúsculas. **Ano:**
  intervalo "de/até". **Dificuldade:** intervalo de 1 a 5.
- **Filtro "só sem categoria"** para achar questões ainda não classificadas.
- **Excluir categoria não apaga questões:** as questões e as subcategorias sobem
  para a categoria-mãe (ou ficam sem categoria, se for de primeiro nível).
- **Mesclar categorias:** as questões e as subcategorias da origem vão para o
  destino. Subcategorias com o mesmo nome são mescladas também, recursivamente.
  **Mover para…** usa a mesma regra quando já existe uma irmã com o mesmo nome.
- **Renomear para um nome já existente** (categoria no mesmo nível, ou tag) é
  recusado com a sugestão de usar "Mesclar".
- **Tags** não diferenciam maiúsculas ("Limites" = "limites"). Prevalece a grafia
  da primeira vez em que a tag foi criada.
- **Ações nos gerenciadores** (renomear, mover, mesclar, excluir) são gravadas
  quando a ação é confirmada no próprio diálogo. Funcionam como o botão "salvar"
  dessas operações.
- **Exclusão de questões:** pede confirmação e aceita várias de uma vez. Se a
  questão excluída estiver aberta no cadastro, o conteúdo continua lá como uma
  questão nova não salva.

## Etapa 3: macros, prévia exata e checagem ao salvar

- **Onde fica o preâmbulo/macros:** em `configuracoes.json` do banco, porque as
  macros fazem parte do conteúdo das questões e precisam valer em todos os
  computadores. Ele entra no lugar de `<<macros>>` no modelo de prova.
- **Macros na prévia rápida:** `\newcommand`, `\renewcommand`, `\providecommand`
  (com ou sem `*`, com número de argumentos e valor padrão), `\DeclareMathOperator`
  (e `*`) e `\def` simples são lidos do preâmbulo e passados ao MathJax
  (`tex.macros`). Pacotes e outros comandos são ignorados na prévia rápida.
  Macros não definidas aparecem em vermelho na prévia rápida.
- **Marcadores dentro de comentários** (`% <<macros>>`) não são substituídos.
  Assim o modelo pode documentar os próprios marcadores.
- **Motor de compilação:** usa o `pdflatex` diretamente. Se ele não for achado e o
  `latexmk` for, usa `latexmk -pdf`. A busca segue esta ordem: caminho
  configurado (arquivo ou pasta), `PATH`, e os locais usuais do MiKTeX e do TeX
  Live no Windows (`%LOCALAPPDATA%\Programs\MiKTeX`, `C:\Program Files\MiKTeX`,
  `C:\texlive\20xx\bin\windows`) e no Linux (`/usr/bin`, `/usr/local/texlive`).
- **Segurança:** além de nunca passar `--shell-escape`, o shell-escape é desligado
  explicitamente: `-no-shell-escape` no TeX Live e `--disable-write18` no MiKTeX
  (detectado pela saída de `--version`). Também são usados
  `-interaction=nonstopmode`, `-halt-on-error` e `openout_any=p`. No Windows o
  processo roda sem janela de console. No tempo limite, a árvore de processos é
  encerrada (grupo de processos no Linux, `taskkill /T` no Windows).
- **Tempos limite:** 30 s para prévia/checagem e 180 s para cada PDF da
  exportação, configuráveis por máquina.
- **Prévia exata:** compila, com o preâmbulo do **modelo padrão** e as macros, a
  questão como ela sai na prova. Logo abaixo vêm a resposta, os comentários das
  alternativas e a resolução. As páginas viram imagens (PyMuPDF, 150 dpi), com as
  margens em branco cortadas. O botão "Compilar prévia exata" não compila
  automaticamente, e um aviso indica quando a questão mudou depois da última
  compilação.
- **Checagem ao salvar:** um único documento contém todos os campos LaTeX da
  questão (enunciado, alternativas/afirmativas, comentários, resposta esperada,
  resolução), cada um em linhas conhecidas. Como o `-halt-on-error` para no
  primeiro erro, o app mostra um erro por vez. O campo é achado pela linha `l.N`
  do log. Em erros sem número de linha (por exemplo "Runaway argument"), o trecho
  citado pelo TeX é procurado no documento. Erros antes de `\begin{document}` são
  atribuídos ao preâmbulo/macros. A mensagem original aparece junto com uma
  explicação em português e o trecho perto do erro, e o log completo pode ser
  aberto. "Corrigir" leva o cursor ao campo com problema.
- **A checagem pode ser desligada** em Configurações > LaTeX. Sem TeX instalado,
  ela é pulada silenciosamente; a barra de status mostra "TeX não encontrado".
- **Comandos extras nas resoluções** (`\marcacorreta`, `\marcavf`, `\comentario`,
  `\respostaesperada`, `\respostaalternativa`, `\semresolucao`, ambiente
  `resolucao`) são definidos com `\providecommand`. Para mudar a aparência, basta
  redefini-los nas macros ou no modelo.
- **Modelos de prova:** criados, editados, importados, duplicados e excluídos em
  Configurações > Modelos de prova, cada ação com seu próprio botão de
  salvar/confirmar. Ao salvar ou importar, o modelo é validado: o app avisa se
  faltarem marcadores ou as definições de `questao`, `alternativas`,
  `afirmativas`, `\alt`, `\afirmativa`, `\espacoresposta` e `\respostacurta`.

## Etapa 4: montagem, versões e exportação

- **Montagens salvas** ficam na tabela `montagens` do banco, em JSON: cabeçalho,
  questões (com valor, espaço e origem), regras, versões, opções e semente. Ao
  reabrir, questões que foram excluídas do banco saem da montagem com um aviso.
- **Valor da questão** é texto livre (ex.: `1,5`), usado como argumento opcional
  de `\begin{questao}[1,5]`. O total aparece na tela quando todos os valores são
  números.
- **Espaço para resposta** em centímetros, só para questões discursivas
  (`\espacoresposta{4cm}`). Zero significa nenhum espaço extra.
- **Sorteio:** cada regra tem um identificador. O botão "Sortear" refaz o sorteio
  de todas as regras e mantém as questões escolhidas à mão. "Ressortear" troca uma
  questão sorteada por outra da mesma regra que ainda não esteja na prova. Questões
  escolhidas à mão não são ressorteadas. A mesma questão nunca entra duas vezes.
  O sorteio das questões usa o acaso comum; quem fica registrado é o resultado
  (a lista de questões), e não uma semente.
- **Versões e semente:** cada versão usa um gerador aleatório próprio, inicializado
  com `"bancoq:<semente>:<índice da versão>"`. Assim, a mesma montagem (mesmas
  questões na mesma ordem, mesmas opções, mesma semente) gera sempre as mesmas
  versões, em qualquer computador. Com "embaralhar questões" ligado, todas as
  versões são embaralhadas, inclusive a A. O app tenta não repetir a mesma ordem
  em duas versões. As afirmativas de V/F também são embaralhadas pela opção
  "embaralhar alternativas" e respeitam o "não embaralhar" da questão. A semente
  é gerada ao criar a montagem, pode ser editada ou trocada ("Nova semente") e
  fica registrada no comentário de cada `.tex`, no gabarito e no `montagem.json`.
- **Máximo de 26 versões** (A a Z). Com uma só versão, `<<versao>>` fica vazio e
  o modelo genérico não mostra "Versão".
- **Arquivos exportados:** `prova_X.tex/.pdf` e `resolucao_X.tex/.pdf` para cada
  versão; um único `gabarito.tex/.pdf`, com um resumo lado a lado das respostas de
  múltipla escolha e V/F de todas as versões e uma tabela completa por versão
  (número na prova, número no banco, resposta, valor); `midia/` com as imagens; e
  `montagem.json` (semente, ordem das questões e das alternativas, respostas).
  Questões discursivas aparecem no gabarito como "ver resolução".
- **Resolução e gabarito usam o preâmbulo do modelo escolhido** (com as macros).
  Assim, os ambientes personalizados valem também nesses documentos, sem precisar
  de outro modelo.
- **Cabeçalho em LaTeX:** os campos do cabeçalho entram no `.tex` como estão, sem
  escapar caracteres especiais. Assim é possível usar matemática ou formatação.
- **Compilação dos PDFs:** duas passadas por documento (para referências como
  `LastPage` em modelos personalizados). Os arquivos auxiliares são apagados quando
  a compilação dá certo; em caso de erro, o `.log` fica para consulta. A
  exportação roda em segundo plano, com barra de progresso e botão de cancelar.
- **Pasta de saída:** os arquivos são gravados diretamente na pasta escolhida. Se
  já houver arquivos com os mesmos nomes, o app pede confirmação antes de
  substituir. Exportar não grava nada no banco.

## Etapa 5: importação de .tex

- **Padrões registráveis:** cada padrão é uma classe em
  `bancoq/nucleo/importador/` que implementa `pontuar(corpo)` e `separar(corpo)`
  e se registra com `@registrar`. No modo "Automático" vence o padrão com a maior
  pontuação. Padrões incluídos:
  - **Classe exam:** `\question`, `\titledquestion`, ambientes `choices`,
    `oneparchoices`, `checkboxes`, `oneparcheckboxes`, `\choice` e
    `\CorrectChoice`, `solution` (e as variantes `solutionorbox`/`lines`/…), e
    `\fillin[resposta]` (vira questão de resposta curta). `parts`/`\part` são
    convertidos para `enumerate`, porque esses ambientes só existem na classe exam.
  - **Lista enumerate:** cada `\item` de primeiro nível é uma questão. Uma lista
    aninhada no **fim** do item vira alternativas quando tem rótulos com letras ou
    itens curtos. Uma lista no meio do texto, ou com itens longos, fica no
    enunciado (questão discursiva).
  - **Títulos "Questão N":** `\textbf{Questão 1}`, `\section*{Questão 2}` ou
    "Questão 3." no início da linha.
  - **Separador manual:** linhas contendo só `%%%`. Sem separador, todo o texto
    vira uma questão, que pode ser dividida na revisão.
- **Reconhecimento dentro de cada questão:** a alternativa correta é marcada por
  `\CorrectChoice`, `\correta`, `\certa`, `\checkmark` ou `(correta)`, ou ainda
  por `\item[*]`/`\item[\checkmark]`. Itens começados por `(V)`/`(F)`/`( )`
  indicam verdadeiro ou falso. A resolução vem dos ambientes `solution`,
  `resolucao`, `solucao`, `proof` ou de um parágrafo "Resolução:"/"Solução:".
- **Comentários** (`%`) são removidos antes da análise; uma questão comentada não
  é importada.
- **Imagens:** `\includegraphics{arquivo}` é procurado na pasta do `.tex`, com ou
  sem extensão. A imagem vira um marcador `[[img:…]]` (`width=0.4\textwidth`
  vira 0.4; medidas em cm são convertidas aproximadamente) e fica pendente até a
  gravação. `figure`, `\caption` e `\label` são retirados, e o conteúdo fica.
- **Macros do arquivo:** as definições (`\newcommand`, `\DeclareMathOperator`,
  `\def`…) do preâmbulo importado que ainda não estão no seu preâmbulo aparecem
  numa faixa amarela. O botão "Ver e adicionar às minhas macros…" as acrescenta a
  Configurações, só depois de confirmar.
- **Revisão:** na lista de questões é possível marcar quais entram, juntar com a
  próxima, dividir no cursor (o texto depois do cursor vira outra questão e leva
  junto as alternativas e a resolução), excluir, editar o tipo, o enunciado, as
  alternativas, a correta e a resolução, e aplicar categoria, tags, fonte, ano e
  dificuldade a várias questões selecionadas de uma vez. A fonte sugerida é o
  nome do arquivo.
- **Gravação:** acontece só no botão "Gravar no banco" (com confirmação) e numa
  única transação. Se houver erro, nada é gravado. As categorias novas escolhidas
  na revisão são criadas nesse momento.

## Etapa 6: trava, backups e duplicadas

- **Trava (`banco.trava`):** JSON com o nome do computador, o usuário, o horário,
  o PID e um identificador de sessão. Ao abrir:
  - sem trava: o app cria uma e abre normalmente;
  - trava de **outro computador**: aviso com as opções "Abrir só para leitura",
    "Abrir assim mesmo" (a trava passa a ser deste computador) e "Cancelar";
  - trava **deste computador** com o app fechado (sobrou de uma queda): é
    reaproveitada sem perguntar;
  - trava deste computador com o processo ainda vivo (o banco aberto em outra
    janela): o mesmo aviso.
  A trava só é removida pela sessão que a criou. Assim, fechar uma janela antiga
  não apaga a trava de outra abertura. Um arquivo de trava ilegível (por exemplo,
  conflito de sincronização) é tratado como de "computador desconhecido".
  Limitação: o rclone sincroniza de tempos em tempos, então a trava só chega ao
  outro computador depois da próxima sincronização.
- **Somente leitura:** o SQLite é aberto com `mode=ro`. Os botões de salvar,
  excluir, gravar importação e salvar montagem ficam desativados, e as
  configurações do banco também. Nesse modo, nem a trava nem o backup automático
  são gravados.
- **Backups:** ficam em `<banco>/backups/` (dentro da pasta sincronizada, para
  existirem em todos os computadores), com o nome
  `backup-AAAAMMDD-HHMMSS-<computador>.zip`. Cada backup contém
  `banco.sqlite3` (cópia consistente pela API de backup do SQLite),
  `configuracoes.json`, `modelos/` e `midia/`; ficam de fora `backups/` e a
  trava. O backup automático roda em segundo plano logo após abrir o banco (não
  ao criar um banco novo). Só os últimos N são mantidos (padrão 10, configurável
  em Configurações > Banco).
- **Restaurar:** em Arquivo > Backups…. Antes de restaurar, o app grava um backup
  do estado atual (`…-antes-de-restaurar.zip`). O conteúdo do .zip é conferido
  (precisa ter `banco.sqlite3` íntegro, sem caminhos fora da pasta). O banco e os
  modelos são substituídos; arquivos de mídia que faltam são copiados (os
  existentes têm o mesmo nome-hash). Depois, as telas são recarregadas.
- **Exportar/importar o banco inteiro:** a exportação gera um .zip com o mesmo
  conteúdo do backup. A importação extrai o .zip numa pasta **nova** (nunca por
  cima de um banco existente) e oferece abrir o banco importado.
- **Duplicadas:** a normalização remove comentários, marcadores de imagem,
  `\begin`/`\end`, nomes de comandos (`\textbf`, `\int`, `\,`…), chaves, `$`, `~`,
  `&`, espaços e acentos, e passa tudo para minúsculas. Os caracteres escapados
  (`\%`, `\$`…) ficam. A comparação usa `rapidfuzz.fuzz.ratio` (0–100) contra
  todos os enunciados do banco. O limite padrão é 85%, configurável. Enunciados
  muito curtos (menos de 12 caracteres depois de normalizados) não são
  comparados, para evitar falsos positivos como "Calcule:".
- **Quando a checagem de duplicadas roda:** ao salvar uma questão nova, ou uma
  existente cujo enunciado mudou. Depois da checagem de LaTeX, o diálogo mostra
  lado a lado a questão nova e as parecidas (com a porcentagem), com as opções
  "Salvar mesmo assim" e "Voltar sem salvar". Na revisão da importação, as
  possíveis duplicadas aparecem marcadas com ⚠ e o número da questão parecida.

## Etapa 7: empacotamento

- **PyInstaller no modo pasta ("onedir")**, e não arquivo único: o arquivo único
  teria de extrair cerca de 450 MB numa pasta temporária a cada abertura, o que
  deixaria o app lento para abrir. No Linux, a pasta vai num `.tar.gz` e numa
  **AppImage** (gerada com o `appimagetool`, runtime "type2", que não depende do
  `libfuse2` do sistema na maioria das distribuições). No Windows, vai numa pasta
  com `BancoQuestoes.exe` e num `.zip`.
- **Poda do Qt:** o PySide6 arrasta módulos que o app não usa (3D, Charts,
  Multimedia, QML/Quick Controls, Location…), os plugins QML e as traduções de
  dezenas de idiomas. O `.spec` retira essas partes e mantém só as traduções em
  português e os locales `pt-BR`/`en-US` do Chromium. A pasta caiu de 656 MB para
  cerca de 475 MB; a AppImage tem cerca de 190 MB. O QtWebEngine continua
  completo (ele precisa de QtQml, QtQuick, QtPositioning e QtWebChannel).
- **`--autoteste`:** opção escondida do executável que confere, numa pasta
  temporária, o SQLite/FTS5, o PyMuPDF, o rapidfuzz, as traduções, o MathJax no
  QtWebEngine e (se houver TeX) a exportação com PDF. Ela é usada nos scripts e no
  GitHub Actions; com `--relatorio arquivo.txt` grava o resultado (no Windows o
  `.exe` não tem console).
- **Rede:** o executável foi testado sob `strace` durante o autoteste. As únicas
  conexões foram a sockets locais (X11 e D-Bus), sem nenhuma conexão TCP/UDP.
- **Compatibilidade no Linux:** o executável depende da glibc da máquina onde foi
  gerado. O workflow do GitHub gera no Ubuntu 22.04 (glibc 2.35), que roda no
  Linux Mint 21 e 22. O build feito neste ambiente usou o Ubuntu 24.04
  (glibc 2.39), que roda no Mint 22.
- **Python do build:** o workflow do GitHub usa o Python 3.12. O build e os
  testes locais usaram o 3.13.
