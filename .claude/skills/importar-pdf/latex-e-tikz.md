# LaTeX e TikZ no banco

Cada campo é um trecho de LaTeX que o aplicativo põe dentro do modelo de prova
(classe `article`, com `amsmath`, `amssymb`, `graphicx`, `enumitem` e as macros do
banco que aparecem em `catalogo` → `preambulo`). Escreva só o conteúdo: nada de
`\documentclass`, `\begin{document}` ou `\item` de alternativas.

## Texto

- Parágrafos separados por linha em branco; não use `\\` para quebrar parágrafo.
- Ênfases do original: `\textbf{}`, `\emph{}`. Listas: `itemize`/`enumerate`
  (para itens a), b): `\begin{enumerate}[label=\alph*)]`).
- Centralizar: `\begin{center} ... \end{center}`.
- Tabelas: `tabular` simples (`\hline`, `|c|c|`), dentro de `center`.
- Aspas: “assim” (caracteres Unicode) ou ``assim''. Travessão: `---` ou —.
- Citação de fonte do texto-base ("Disponível em: …") vai no fim do enunciado,
  em `{\small ...}`.

## Matemática (convenções brasileiras)

- Fórmulas em `$...$`; destacadas em `\[ ... \]` (não use `$$`).
- Vírgula decimal: `$3{,}5$`. Milhar com espaço fino: `$12\,023$`.
- Multiplicação: `\cdot` (ou `\times` se o original usa ×). Divisão: `\div` se o original usa ÷.
- Graus `$60^\circ$`; porcentagem `$25\%$`; dinheiro `R\$~1\,250{,}00`.
- Unidades em texto: `$5\ \text{cm}$`, `$3\ \text{m}^2$`.
- Conjuntos `\mathbb{N}`, `\mathbb{Z}`, `\mathbb{R}`; intervalos como no original.
- Ângulos `\widehat{ABC}`, segmentos `\overline{AB}`, arcos `\overset{\frown}{AB}`
  (como no original).
- Não use pacotes que não estejam no preâmbulo; se precisar mesmo, declare com
  `@preambulo:` (ex.: `@preambulo: \usepackage{xcolor}`) e o professor decide no app.

## Prévia rápida do aplicativo

A prévia rápida entende parágrafos, `\textbf`, `\emph`, listas, `center`, `tabular`
simples e toda a matemática (MathJax); figuras TikZ aparecem como imagem. O resto
aparece só na prévia exata (compilada). Prefira esses recursos.

## TikZ

Toda questão com figura precisa de `@preambulo: \usepackage{tikz}` e, se usar,
`@preambulo: \usetikzlibrary{angles,quotes}` (só as bibliotecas usadas). Para
gráficos de funções com eixos, `pgfplots`: `@preambulo: \usepackage{pgfplots}` e
`@preambulo: \pgfplotsset{compat=1.17}`.

### Como desenhar

1. Olhe o original e escolha coordenadas simples que reproduzam as **proporções e
   posições** (um quadriculado imaginário ajuda). Medidas, ângulos e rótulos têm de
   ser os do original; o que a questão pede para descobrir não pode ficar "visível"
   no desenho de um jeito que o original não mostra.
2. Tamanho parecido com o original: em geral 4 a 8 cm de largura (`scale=` ajusta).
3. Rótulos em modo matemático: `node[above] {$A$}`; medidas `node[midway, below] {$6$ cm}`.
4. Traço como o original: contínuo, `dashed`, `thick`; pontos `\fill (x,y) circle (1.5pt);`.
   Ângulo reto: `\draw (x,y) rectangle ++(0.25,0.25);` ou a biblioteca `angles`.
5. Cor só quando o original usa cor com significado (ex.: números pretos e brancos,
   regiões sombreadas): `fill=gray!30`, `red!60`, `pink!60` etc. (o TikZ já carrega
   o `xcolor`). Sombreado cinza do original: `fill=gray!25`.
6. Figura dentro de `\begin{center} ... \end{center}`. Em alternativas com figura,
   a `tikzpicture` vai dentro da alternativa (com `scale` menor).

### Compilar e comparar

1. Escreva a questão com o TikZ e rode `./bancoq-ia tikz <pacote> <id>`.
2. Para cada figura vem `ok` (compilou) e `comparacao` (PNG com o original à esquerda
   e o seu desenho à direita). Abra a comparação e confira: forma, proporções,
   posição dos rótulos, o que está tracejado/sombreado, nada faltando ou sobrando.
3. Erro de compilação vem em `erro` (com a linha perto do problema). Corrija.
4. No máximo **3 rodadas** por figura. Se ainda não estiver fiel, deixe a melhor
   versão e marque `@figura: N | ajustar | <o que difere>`.
5. Para experimentar um desenho difícil antes de escrever a questão:
   `./bancoq-ia tikz <pacote> <id> --arquivo trabalho/<pacote>/rascunho.tex --figura N`.

### Casos especiais

- **Tabela ou quadro de texto** detectado como figura: escreva em LaTeX comum
  (`tabular`) e marque `@figura: N | texto`.
- **Foto, ilustração ou símbolo desenhado à mão** (ex.: hieróglifos): desenhe uma
  aproximação simples e reconhecível com TikZ e marque `ajustar`, dizendo na nota
  que o original é uma ilustração. Se o símbolo se repete (alternativas montadas com
  os mesmos símbolos), repita o mesmo código em cada `tikzpicture`: cada figura é
  compilada sozinha na conferência, então não dependa de definições feitas em outra.
- **Gráfico de função** com eixos: `pgfplots` (`axis lines=middle`) ou eixos à mão
  com `\draw[->]`; marque nos eixos só os valores que o original mostra.
- **Figura falsa** (logotipo, moldura, ícone decorativo): `remover-figura` e nada de
  `@figura` para ela.
