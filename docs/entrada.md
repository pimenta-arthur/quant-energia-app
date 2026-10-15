# Caixa de entrada (arquivos baixados → raw/)

Os arquivos brutos entram no app por `data/entrada/<fonte>/`. Cada funcionalidade lê só as pastas das
suas fontes (bandeiras abaixo; PLD horário na seção própria). Você solta o arquivo **como baixou**
(zip, PDF, txt, xlsx, csv; solto ou dentro de uma pasta, com zips dentro de zips se for o caso) na pasta
da fonte e roda:

```bash
uv run qe bandeiras atualizar      # entrada → raw/ → tratamento → backtest → status e prévia (não publica)
uv run qe bandeiras ingerir        # só a primeira parte: entrada → raw/
```

As pastas são criadas na primeira execução. Na ingestão, para cada item da pasta da fonte:
1. identifica o mês (ou a emissão, ou o ano) **pelo conteúdo**; se o conteúdo não disser, pela subpasta
   `AAAA-MM` em que o item estiver (ex.: `entrada/ons_pmo/2026-10/renovaveis.csv`);
2. grava em `raw/` só os arquivos que o modelo usa, idênticos aos originais (tirados do zip, se for o caso);
3. relê o que gravou e confere o hash;
4. só então **apaga o original** da entrada. Se algo falhar, o original fica onde está e o motivo aparece
   no terminal e em `entrada/relatorios/<data e hora>.txt`.

Não há segunda cópia: depois da ingestão, o dado existe só em `raw/`.

## Fontes

| Pasta | O que soltar | Vai para `raw/` | Como o mês é identificado |
|---|---|---|---|
| `ccee_newave/` | zip do deck do NEWAVE (ou os arquivos soltos numa pasta) | `ccee_newave/deck=AAAA-MM/v=<hash>/`: `ghtotsin.out`, `eafbm001…004.out`, `cmarg001…004.out`, `cmarg001…004-med.out`, `sistema.dat`, `c_adic.dat` + `_ingestao.json` | cabeçalho do `ghtotsin.out` ("PMO - OUTUBRO - 2026") |
| `ons_pmo/` | `relato.rv0`, PDF da ENA (Tabela 6) e `renovaveis.csv` do PMO revisão 0 (zip ou pasta) | `ons_pmo/AAAA-MM/relato.rv0`, `ena.pdf`, `renovaveis.csv` | cabeçalho do relato ("PMO - OUTUBRO/26") e texto do PDF ("OUTUBRO/2026"); o `renovaveis.csv` não traz o mês: só entra junto do relato/ENA ou numa subpasta `AAAA-MM` |
| `ccee_infobandeira/` | PDF do boletim InfoBandeira | `ccee_boletim/AAAA-MM/infobandeira.pdf` | texto do PDF ("Nº 102 - outubro/2026") |
| `ecmwf/` | `.txt` de ENA (`ENA_MLT_SUBSISTEMA_MENSAL_ECENSLT…_AAAAMMDD.txt`): média, percentis e 51 membros (soltos ou em zip) | `ecmwf/emissao=AAAA-MM-DD/<mesmo nome>` | data no fim do nome do arquivo |
| `ccee_patamares/` | `AAC001…xlsx` do ano (o AAC002 não é usado) | `ccee_patamares/AAAA/AAC001.xlsx` | ano das horas do arquivo |
| `aneel_bandeiras/` | csv do histórico de bandeiras (dados abertos) | `aneel_bandeiras/historico.csv` | — (conjunto inteiro, sempre substitui) |

Antes de aceitar, a ingestão roda o leitor do `qe_core` sobre o PDF da ENA, o boletim, o AAC001 e o csv
da ANEEL: arquivo que não passa na leitura fica na entrada.

## Regras
- **Versões:** o deck do NEWAVE tem versão = hash do conteúdo dos 15 arquivos; um deck republicado no mesmo
  mês entra como versão nova, ao lado da anterior. O ECMWF é guardado por emissão: uma emissão extra
  (ex.: dia 15) entra separada da do dia 1. A projeção usa a versão e a emissão mais recentes.
- **Imutabilidade:** arquivo já gravado em `raw/` e diferente do novo não é substituído; o novo fica na
  entrada com aviso. Para substituir de propósito: `--sobrescrever` (exceto o histórico da ANEEL, que
  sempre substitui).
- **Arquivos extras** dentro de um zip (o deck completo, outros relatórios do PMO) são ignorados; só entra o
  que o modelo usa.
- Um arquivo ainda sendo copiado (zip pela metade) é recusado e fica para a próxima execução.
- O formato real dos downloads de cada fonte (nomes dos zips, estrutura interna) deve ser conferido na
  primeira vez: se algo não for reconhecido, a mensagem diz o que faltou.

## PLD horário

```bash
uv run qe pld_horario atualizar    # entrada → raw/ → tratamento do que mudou → status (não publica)
uv run qe pld_horario publicar     # regrava os dados da página (sem registro de rodada)
uv run qe pld_horario status       # último deck, último PLD publicado, dias calculados e lacunas
```

| Pasta | O que soltar | Vai para `raw/` | Como é identificado |
|---|---|---|---|
| `ccee_dessem/` | deck do DESSEM: o mensal `DES_AAAAMM.zip` ou os diários `DS_CCEE_MMAAAA_SEMREDE_RVnDdd.zip` (entrada) e `Resultado_DS_CCEE_…zip` (resultado), soltos ou numa pasta | `ccee_dessem/dia=AAAA-MM-DD/`: `entdados.dat.gz`, `renovaveis.dat.gz`, `PDO_SIST.DAT.gz`, `PDO_OPER_USIH.DAT.gz` + `_entrada.json` e `_resultado.json` (nome do deck, PMO, revisão, hash dos originais) | nome do zip diário: o `MMAAAA` é o mês operativo; na RV0, dias ≥ 20 são do mês civil anterior (`RV0D27` de 10/2026 = 27/09/2026) |
| `ccee_decomp/` | deck do DECOMP: o mensal `DCAAAAMM.zip` ou os semanais `DCAAAAMM-semN[_kaPublicacao].zip` e `Relatorio_Sumario-AAAAMM-semN….zip` | `ccee_decomp/pmo=AAAA-MM/sem=N/pub=K/`: `dadger.gz`, `sumario.gz` | nome do zip semanal (PMO, semana e publicação; sem sufixo = 1ª) |
| `ccee_pld/` | `pld_horario_AAAA.csv` (um por ano, `;`) | `ccee_pld/pld_horario_AAAA.csv` | ano das datas do arquivo |
| `ccee_limites_pld/` | `dados_pld.csv` (limites anuais) | `ccee_limites_pld/dados_pld.csv` | — (conjunto inteiro, sempre substitui) |

- **DESSEM e DECOMP em `.gz`** (exceção à regra "idêntico ao original", decidida na migração em
  2026-10-14): os arquivos usados, descompactados, ocupam o dobro do zip da CCEE (~465 MB/mês contra
  243 MB); em gzip, ~57 MB/mês. O conteúdo é o original sem perda: o hash conferido na gravação e na
  reingestão é o do arquivo descomprimido, e os leitores do `qe_core` leem o `.gz` direto.
- **Um deck por dia**, em duas metades que podem chegar separadas (entrada e resultado): o dia só é
  tratado quando as duas estão em `raw/`; `status` lista os dias incompletos. O zip mensal cresce ao
  longo do mês: baixá-lo de novo não duplica nada (dias já gravados dão "igual").
- Antes de aceitar, a ingestão confere o dia do caso (registros TM do `entdados.dat` e "Data do
  Caso" do `PDO_SIST.DAT`) e roda os leitores do dadger e do sumário. O `PDO_OPER_USIH.DAT` é
  opcional (ausente ou truncado em alguns decks: o dia fica sem esse dado).
- **DECOMP republicado** (`_2aPublicacao`) entra como `pub=2` ao lado da 1ª; o tratamento usa a
  última publicação de cada semana.
- **PLD publicado**: o csv do ano corrente é republicado a cada atualização da CCEE e substitui o
  anterior, desde que não perca horas já publicadas (se perder, fica na entrada; `--sobrescrever`
  aceita). Nos dias com deck e ainda sem publicação, o tratamento calcula o PLD do deck pela regra
  oficial e o substitui quando o csv chegar.

## Na AWS
`data/entrada/` vira `s3://<bucket>/entrada/<fonte>/`, e um upload dispara a ingestão; coletores
automáticos (quando houver) gravam nas mesmas pastas.
