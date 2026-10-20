# Padrão visual Quant Energia · v1.2 · 2026-10

Guia das páginas do Quant Energia (bandeiras tarifárias, PLD horário) para reaproveitar o mesmo layout em
páginas e projetos novos. Matriz em `quant-energia-app/web/padrao/`; em outro projeto, **copiar a pasta
inteira** (sem apontar para o repositório de origem) e manter a versão no topo de cada arquivo.

## Arquivos

| Arquivo | O que é | Quando usar |
|---|---|---|
| `base.css` | cores (claro e escuro), fontes, texto, cartões, tabelas, navegação, componentes de metodologia | todas as páginas |
| `painel.css` | topo com premissas, blocos, grades, abas, legendas curtas, tooltip, cartões de número, pequenos múltiplos, marcadores de cenário, espaçamento compacto | páginas de painel (projeções, acompanhamento) |
| `graficos.js` | funções de SVG, tooltip, eixos, rótulos e números em pt-BR, sem biblioteca | páginas com gráficos |
| `modelo.html` | catálogo com cada componente uma vez, dados fictícios | ponto de partida de uma página nova |

Página nova: copiar `modelo.html`, trocar textos e dados, apagar o que não usar. Ordem dos estilos:
`base.css` → `painel.css` → estilos da própria página (no `<style>` ou num `pagina.css`). Metodologia: só
`base.css` (layout de texto, ~70 caracteres por linha).

## Estrutura da página
1. **Navegação** no topo: marca à esquerda (link para a página inicial), páginas à direita, a atual sublinhada.
2. **Topo** (`.hero`): rótulo em caixa alta com o horizonte, título institucional, linha de **premissas**
   (insumos, versões, modelo) e, à direita, a data da rodada (`.meta .atualizado`).
3. **Seções** com `h2` que descreve o conteúdo; o principal primeiro (resultado), depois os fundamentos,
   depois o desempenho e a metodologia.
4. Cada gráfico num **bloco** (`.bloco`): título curto (`.ttl`), seletores à direita (`.barra-abas` + `.abas`),
   o gráfico, e a **legenda curta embaixo** (`.leg`).
5. **Avisos** no fim (`.aviso`): premissas e aproximações, em uma ou duas frases, com link para a metodologia.

## Texto
- Português do Brasil, com acentuação; números no formato pt-BR (`n()`, `pct()`, `sn()` de `graficos.js`).
- Títulos institucionais que dizem o que o gráfico mostra ("Posicionamento no ábaco regulatório"), sem
  pergunta ou slogan; mesmo tamanho para os títulos de seção.
- **Escala de títulos única** (v1.2, em `base.css`): h1 e h2 `1.5rem`, h3 `1.02rem`, nos painéis e nas metodologias. Não
  redefinir o tamanho de h1, h2 ou h3 na página (exceção: títulos de blocos pequenos, como `.mini .ttl`). Espaçamento
  entre seções (`main`): 56 px nas páginas de texto (só `base.css`) e 34 px nos painéis (`painel.css`); sem valor próprio
  por funcionalidade.
- **Marca e menu:** o link "Quant Energia" (`.nav .marca`) tem o mesmo tamanho em todas as páginas; classes locais não
  usam o nome `.marca` (colidia com a marca do menu). Último item do menu: Metodologia.
- Legendas curtas: o que é cada marca e de onde vem o dado. Explicação longa vai para a metodologia.
- Datas: `09/10/26` (e `22:55`, discreto, quando há mais de uma publicação no dia); meses: `out/26`.
- Rótulos padronizados numa mesma coluna: um formato só (ex.: todas as linhas com data; subtexto curto
  com o que mudou). Siglas em maiúsculas (DECK, ECMWF), demais palavras com inicial maiúscula.

## Cores com função
- **Neutros** (`--bg`, `--surface`, `--ink`, `--ink-2`, `--ink-3`, `--rule`): fundo, texto e linhas de grade.
- **Destaque** (`--accent`, azul): o valor esperado / a projeção principal, botões e abas selecionados.
- **Oficial / realizado**: linha cheia em `--ink`.
- **Cenários**: esperado `--cen-esp` (azul), seco `--cen-li` (laranja), úmido `--cen-ls` (verde-azulado);
  faixa entre cenários em `--faixa-proj`.
- **Bandeiras** (`--vd`, `--am`, `--v1`, `--v2`, e `--esc` na página das bandeiras): só para bandeira tarifária.
  Texto sobre amarelo em `--on-am` (escuro); sobre as demais, `--on-flag` (branco).
- **Erro com sinal**: `fundoErro(e, escala)`: azul quando acima do oficial, vermelho quando abaixo, mais forte
  quanto maior o erro; neutro quando não há oficial.
- Toda cor nova entra como token em `:root` e é redefinida para o tema escuro (nos dois blocos: `@media
  (prefers-color-scheme: dark)` e `:root[data-theme="dark"]`).

## Gráficos
- SVG desenhado com `S()`; tooltip com `dicaEm()` em todo ponto ou barra (a página precisa de
  `<div class="dica" id="dica" hidden></div>`). Tooltip com o mês, o valor e a referência (oficial, anterior).
- Tooltip quebra linha (largura máxima de 280 px, nunca maior que a tela; a página pode aumentar o máximo) e troca de
  lado perto da borda direita ou de baixo da tela (`dicaEm`, desde a v1.1): a página não precisa reposicionar.
- **Nada de marcador colorido sobre fundo colorido.** Sobre faixas que já têm cor (ábaco, regiões),
  cenários viram marcador neutro: círculo branco, contorno escuro e letra (`.cen-marca-svg`, legenda com
  `i.cen-marca`); ligações em cinza tracejado.
- Eixo de tempo em painel estreito: rótulo só em jan e jul (`rotuloDeMes`); a data exata fica no tooltip.
- Rótulos que caem no mesmo ponto: `empilharRotulos()` (em ordem cronológica, o mais próximo embaixo).
- Linha vertical tracejada marca a data da previsão ("deck"); referência fixa (piso, limiar) em tracejado `--ink-3`.
- Projeções futuras com contorno tracejado em tabelas de células; faixa clara para o intervalo de cenários.
- Pequenos múltiplos (`.mini6` + `.mini`) sempre com a **mesma escala** e o horizonte (`M+1`) no título.
- Tabelas de células coloridas (cores por mês e linha): quadrados simples de cor, sigla curta dentro,
  ✗ no canto quando difere do oficial, ▲▼ quando muda em relação à linha anterior.

## Layout
- Largura máxima de 1080 px; texto corrido em ~70 caracteres; espaçamento compacto do `painel.css`.
- Sem rolagem horizontal da página: tabelas largas rolam dentro do próprio bloco (`.rolagem`) com a
  coluna de rótulos fixa.
- Funciona no celular (grades com `auto-fit`); temas claro e escuro conferidos antes de publicar.
- Fontes: IBM Plex Sans (texto) e IBM Plex Mono (números, eixos, rótulos), do Google Fonts.

## Versões
- v1.2 (2026-10-20): escala de títulos única no `base.css` (h1 e h2 1,5 rem, h3 1,02 rem; as metodologias deixam de ter
  h1 grande), espaçamento entre seções sem valor por funcionalidade (Risk Lab de 40 para 34 px), regra da marca do menu.
- v1.1 (2026-10-20): tooltip com quebra de linha e troca de lado perto da borda (`graficos.js`, `painel.css`).
- v1 (2026-10): primeira versão.

## Conferência antes de publicar
- Abrir a página nos temas claro e escuro e numa largura de celular.
- Passar o mouse pelos gráficos: todo elemento com valor tem tooltip.
- Procurar sobreposição de rótulos, textos quebrando em várias linhas e cores que se confundem com as do fundo.
