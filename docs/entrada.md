# Caixa de entrada (arquivos baixados → raw/)

Os arquivos brutos entram no app por `data/entrada/<fonte>/`. Você solta o arquivo **como baixou**
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

## Na AWS
`data/entrada/` vira `s3://<bucket>/entrada/<fonte>/`, e um upload dispara a ingestão; coletores
automáticos (quando houver) gravam nas mesmas pastas.
