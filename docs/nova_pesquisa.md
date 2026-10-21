# Como começar uma pesquisa para uma nova funcionalidade (repositório analytics)

Toda funcionalidade do app nasce num repositório de **pesquisa** independente (`<tema>-analytics`), onde o método é
descoberto, testado e documentado. Só depois de validado ele é promovido ao app (`docs/nova_funcionalidade.md`).
Este guia monta esse repositório e descreve o ciclo de trabalho, a partir do que funcionou em
`forecast-bandeiras-analytics`, `risk-lab-dessem-analytics` e, principalmente, `pricing-descolamento-analytics`
(o exemplo mais completo: diagnóstico → modelo → testes pré-registrados → páginas → pacote de promoção).

```
pesquisa (<tema>-analytics)                                   produto (quant-energia-app)
diagnóstico → baseline → modelo → testes → páginas → pacote ──► features/<código>/ + web/<código>/
                                                    (tag promocao-quant-v1)
```

---

## 1. Antes de criar: definir o problema (uma conversa com o Arthur)

Escrever, em uma página, e levar ao Arthur antes de qualquer código:
- **Alvo:** a variável exata, com fórmula e unidade (ex.: `PLD_médio_sub − PLD_médio_SE`, R$/MWh, mensal).
- **Uso:** quem usa, para quê e em que granularidade (mês, trimestre, produto; hora, dia).
- **Insumos disponíveis na data da previsão:** decks, publicações, curva informada pelo usuário. O que é insumo do
  usuário (ex.: a curva do SE da mesa) nunca vem do modelo.
- **Horizonte e cadência** (por deck, por dia, por semana).
- **Saídas:** preço justo, faixa, probabilidade; o que a página precisa mostrar.
- **Código da funcionalidade** (`forecast_bandeiras`, `risk_lab_dessem`, `pricing_descolamento`): usado no repositório
  do app, nas pastas, nos comandos e nas chaves. Decidido pelo Arthur.

---

## 2. Criar o repositório

```bash
cd ~/projects
uv init --package --python 3.14 <tema>-analytics
cd <tema>-analytics
uv add numpy pandas pyarrow matplotlib plotly seaborn statsmodels scikit-learn
uv add --dev pytest ruff ipykernel jupyter
uv run python -m ipykernel install --user --name <tema>-analytics --display-name "Python (<tema>-analytics)"
mkdir -p data/raw data/processed notebooks reports/figures docs tests web
cp -R ../quant-energia-app/web/padrao web/padrao      # cópia do padrão visual, não link
# PowerShell (Windows): Copy-Item -Recurse ..\quant-energia-app\web\padrao web\padrao
git init && git add -A && git commit -m "Estrutura inicial"
gh repo create pimenta-arthur/<tema>-analytics --private --source . --push
```

- **Python 3.14, fixado em `.python-version` e em `requires-python`. Nunca pip.** Pacote novo: `uv add` (`--dev` para
  ferramentas). Se a `.venv` quebrar após atualizar o Python: apagar a `.venv` e `uv sync`.
- **A origem do Python é da máquina, não do projeto.** Sem o 3.14 instalado: `uv python install 3.14` (Windows, Linux ou
  Mac sem Homebrew). No Mac do Arthur, `~/.config/uv/uv.toml` (`python-preference = "only-system"`) faz o `uv` usar o
  Python do Homebrew; esse arquivo é configuração da máquina e não entra no repositório. Os comandos `uv` são iguais
  em qualquer sistema; só os de shell (`cp`, `mkdir -p`, `\`) mudam no Windows.
- Dependências extras só quando a fonte pedir (`openpyxl` para xlsx, `pdfplumber` para PDF).
- `.gitignore`: `.venv/`, caches, `data/` (decidir caso a caso o que versionar e registrar a decisão) e
  `reports/promocao/`.
- **Independente:** não importa código nem lê arquivos de outros repositórios (nada de `uv add --editable ../…`
  nem `sys.path`). Os dados brutos são copiados para `data/raw/` a partir de `energia-data-ingestion`, por uma função
  de extração no próprio repositório.

### Estrutura

```
<tema>-analytics/
├── CLAUDE.md                 # regras do projeto (modelo na seção 3)
├── docs/metodologia.md       # raciocínio, decisões D001…, testes, questões em aberto (seção 4)
├── data/raw/<fonte>/         # originais, SOMENTE LEITURA, uma pasta por fonte
├── data/processed/           # tabelas tratadas (Parquet)
├── notebooks/                # 01_eda, 02_…: só orquestram funções de src/
├── src/<pacote>/             # load.py (leitores), preparar.py (raw → processed), módulos do estudo,
│                             # web.py (dados das páginas), referencias.py (pacote de promoção)
├── tests/                    # vazamento, versão congelada, paridade (seção 7)
├── reports/figures/<estudo>/ # PNG; cada variante numa pasta nova (não sobrescrever análises)
└── web/<tema>/ + web/padrao/ # páginas (seção 8)
```

---

## 3. CLAUDE.md (modelo)

Copiar e preencher. As seções "Como trabalhar", "Ambiente" e "Regra do backtest" valem para todos os projetos.

```markdown
# <tema>-analytics

## Objetivo do projeto
<alvo, uso, insumos, horizonte, saídas: o texto da seção 1>

**Metodologia, decisões e questões em aberto: `docs/metodologia.md`.** Ler antes de propor abordagens e
registrar ali toda decisão (ID, data, motivo, status).

## Fase atual
<o que está valendo e o que está em teste; versão de referência e a tag dela>

## Como trabalhar com o Arthur
- Português do Brasil, com acentuação correta. Explicações didáticas, sem simplificar a matemática, com números reais.
- Não assumir nada como verdade: conferir regras do setor na fonte oficial e dizer quando algo não foi confirmado.
- Opinião técnica própria (inclusive discordar). Hipótese não é premissa.
- Pedido exploratório ("como você faria?"): propor e esperar aprovação. Ordem direta: executar.
- Commit e push só quando pedido; tags nos marcos (versão de modelo, promoção).
- Não sobrescrever análises anteriores; variante nova vai para pasta/arquivo novo.
- Começar sempre por baseline simples; não treinar modelos sem pedido.
- Visual sóbrio (padrão `web/padrao`), títulos que descrevem o gráfico, legendas curtas, tooltips numéricos.

## Comandos
- `uv run python -m <pacote>.preparar`: raw → processed (idempotente).
- `uv run pytest` (inclui vazamento) e `uv run ruff check .`.

## Ambiente
- `uv add` / `uv run`; nunca pip, nunca outro venv. Python 3.14 (`.python-version`). Kernel: `Python (<tema>-analytics)`.
- Sem dependência de outros repositórios.

## Estrutura e convenções
- `data/raw/` somente leitura; `data/processed/` em Parquet; notebooks só orquestram; código e comentários em português.

## Regra do backtest: só o que existia na data da previsão
- Insumos, erros, σ, viés e calibração só com o que estava publicado e com alvos já encerrados na data.
- Treino/teste separados por data, nunca aleatoriamente; transformações ajustadas só no treino.
- Parâmetro escolhido e avaliado na mesma amostra = "dentro da amostra", e é rotulado assim.
- Oráculo (realizado no lugar do previsto) só para estudar limites, sempre rotulado.
- Todo resultado diz o que é fora da amostra, dentro da amostra e oráculo.

## Regras do setor já conferidas
- CMO ≠ PLD: o PLD é o CMO dos decks da CCEE limitado ao piso e ao teto do ano.
- <outras, cada uma com a fonte>
```

---

## 4. docs/metodologia.md (modelo)

É o diário da pesquisa e a fonte do texto da página de metodologia. Seções numeradas, nunca apagadas: um resultado
superado ganha uma nota apontando para a seção nova.

```markdown
# Metodologia: <tema>

Registro do raciocínio, das decisões (D001…) e das questões em aberto. Resultados sempre rotulados como
fora da amostra, dentro da amostra ou oráculo.

## 1. Problema        alvo, uso, saídas, horizonte
## 2. Dados           tabela: fonte | pasta | cobertura | uso
## 3. Fatos observados  o que os dados mostram, com números (antes de qualquer modelo)
## 4. Modelos         baseline primeiro
## 5. Backtest        desenho (decks, meses-alvo, o que é insumo), métricas
## 6. Decisões        tabela: ID | data | decisão | motivo | status
## 7. Limitações e questões em aberto (Q1…)
## N. <cada diagnóstico, versão ou teste numa seção própria, com data, ID e resultado no título>
```

- **Tabela de testes** (uma linha por teste): ID | mudança | base | resultado | decisão. Inclui os não adotados.
- **Fila de testes:** itens pendentes com status, em ordem; atualizar a cada teste (transparência).

---

## 5. Ciclo de trabalho (o arco)

1. **Dados e leitores.** Um leitor por arquivo-fonte (função pura sobre o caminho ou o texto), em `load.py` ou num
   módulo da fonte; `preparar.py` gera `data/processed/`. Conferir contra a fonte oficial (ex.: médias publicadas).
2. **Fatos antes de modelo.** EDA com números: quando o fenômeno acontece, com que frequência, por estação e hora,
   e em que nível dos insumos. Registrar em "Fatos observados".
3. **Diagnóstico físico/estrutural.** Por que acontece: que restrição, que variável explica (ex.: AUC por regime,
   curvas de resposta). O modelo sai daqui, não de uma regressão genérica.
4. **Baseline simples** com backtest honesto (seção 6). É a régua de todas as versões.
5. **Modelo v1** a partir do diagnóstico. Congelar: teste de referência (`tests/test_<versao>.py`), tag
   `modelo-<versão>`, decisão registrada. Esse é o **ponto de partida**.
6. **Testes isolados.** Uma mudança por vez contra o ponto de partida (seção 6). Nada de empilhar mudanças.
7. **Páginas** (seção 8) quando a versão estiver estável; o Arthur avalia e itera.
8. **Pacote de promoção** (seção 9) quando o Arthur decidir levar ao app.

---

## 6. Testes e avaliação

**Pré-registro, antes de rodar** (escrito em `metodologia.md`):
- a mudança, isolada, e a hipótese que ela testa;
- o critério de adoção (ex.: "ganho agregado > 0,5 e nenhum trimestre do ano pior em mais de 0,5");
- os recortes obrigatórios, entre eles a **base treinada** (casos em que a versão de referência já tinha dado
  suficiente; ganho só onde a base não tinha treino não conta).

**Métricas:**
- erro absoluto médio e viés, por agregação (mês, trimestre, semestre) e por ano-alvo;
- **cobertura da faixa sempre junto com a largura e o CRPS** (cobertura sozinha premia faixa larga);
- casos por trimestre do ano, para ver trocas entre estações.

**Alternativas de referência, nos mesmos casos:** zero (ou "nada acontece"), repetir o ano anterior, climatologia
estatística. O modelo só vale o que ganha delas.

**Decisão:** adotado, não adotado ou inconclusivo, registrada antes do próximo teste. Um candidato promissor sem
evidência suficiente vira reteste pré-registrado (com data) e, se útil, modelo-sombra.

**Testes de código (`tests/`):**
- vazamento: nenhuma previsão usa dado posterior à data (ex.: rodar com dados cortados na data e comparar);
- versão congelada: a versão de referência reproduz os números registrados;
- paridade Python × JS quando a página recalcula algo no navegador;
- agregação (média por horas, cenários completos no período).

---

## 7. Rodadas

- Uma **rodada** = uma publicação (insumos vigentes, versão do modelo, data e hora). Registrar num
  `historico.json` versionado; nunca recalcular uma rodada publicada.
- Para comparar rodadas, usar um insumo de referência fixo (ex.: SE plano de R$ 200), assim a diferença vem dos
  dados e do deck, não do usuário.
- Rodadas reconstruídas para o passado (como a versão vigente teria visto) entram com o rótulo `reconstruida`.

---

## 8. Páginas

Partir de `web/padrao/modelo.html` (regras em `web/padrao/GUIA.md`). Três páginas com papéis separados:

| Página | Papel | Conteúdo típico |
|---|---|---|
| `index.html` (produto) | o que o usuário usa | entrada do usuário (ex.: curva), resultado por produto com justo e faixa, sensibilidade, histórico realizado e fundamentos do deck recolhidos |
| `metodologia.html` | como e quão bem funciona | passos em duas camadas (simples + técnico), exemplo de ponta a ponta com números reais, desempenho contra alternativas, casos, limitações, histórico de rodadas, versões, glossário |
| `fundamentos.html` | por que o fenômeno acontece | capítulos curtos com um gráfico e uma conclusão cada; fecha com "do diagnóstico ao modelo" |

- Dados gerados por `web.py` (`dados.js` por página); o texto fixo da metodologia é revisado a cada versão.
- **Contas no Python, desenho no JS.** No navegador só o que depende da entrada do usuário, com teste de paridade.
- Tooltips numéricos e objetivos; textos curtos; avisos no fim, com as premissas e o link para a metodologia.
- Gráficos relevantes também em PNG em `reports/figures/`.
- Revisão com o Arthur pelo artifact (arquivo único com CSS, JS e dados embutidos); site estático opcional.

---

## 9. Pacote de promoção (quando o Arthur decidir levar ao app)

Modelo: `pricing-descolamento-analytics/docs/promocao_descolamento.md` e
`risk-lab-dessem-analytics/docs/promocao_pld_horario.md`. Seções:

1. visão geral (blocos, natureza, maturidade) e **escopo**: o que levar e o que **não** levar, nem como contexto;
2. fontes (o que entra em `raw/`, período, se o app já tem);
3. leitores (e quais já existem no `qe_core`);
4. tabelas-base;
5. blocos (método exato da versão vigente, sem os ramos de teste);
6. ordem de migração;
7. o que muda na página no app;
8. lacunas conhecidas;
9. referências para conferência (geradas por `referencias.py` em `reports/promocao/<data>/`, fora do git, com
   `manifesto.json` de hashes dos dados brutos), com tolerâncias e um exemplo conferido à mão;
10. decisões de arquitetura a tomar no app;
11. mudanças desde a promoção anterior.

Antes de entregar: todo resultado da página gerado por função (nada de chamada avulsa), decisão registrada em
`metodologia.md`, tag `promocao-quant-v1`. A sessão do app recebe um prompt apontando para o pacote, lê tudo,
traz as decisões da seção 10 ao Arthur e implementa bloco a bloco (`docs/nova_funcionalidade.md`).

---

## 10. Prompt para abrir a pesquisa (colar na sessão do novo repositório)

```
Vamos começar a pesquisa de <tema> para uma futura funcionalidade do Quant Energia App. Siga o guia
../quant-energia-app/docs/nova_pesquisa.md: crie o repositório (seções 2 a 4), com CLAUDE.md e
docs/metodologia.md preenchidos a partir do problema abaixo, e pare para eu revisar antes de qualquer análise.

Problema: <alvo, uso, insumos, horizonte, saídas>.
Fontes: <quais, e onde estão em ../energia-data-ingestion>.
Referência de qualidade: ../pricing-descolamento-analytics (docs/metodologia.md e web/descolamento/).
```
