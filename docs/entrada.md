# Formato de entrada (pasta de origem da ingestão)

`qe bandeiras ingerir --origem <pasta> --mes AAAA-MM` lê os arquivos brutos de uma pasta neste
formato. É o formato de entrada do app: qualquer pasta que o siga serve (hoje, por conveniência, a
`data/raw` do forecast-bandeiras-analytics). Na fase AWS, os coletores automáticos gravam direto em
`raw/` com as mesmas chaves que a ingestão produz.

```
<origem>/
├── ons_decomp/<AAAA>/<AAAA>_<MM>/        PMO do ONS (DECOMP revisão 0) do mês
│   ├── relato.rv0                        obrigatório: balanço, térmicas, pequenas usinas, ANDE, EAR
│   ├── ena.pdf                           obrigatório: Tabela 6 (ENA prevista do mês por subsistema)
│   └── renovaveis.csv                    a partir de out/2025: separa eólica e solar do Geol
├── ccee_calculo_bandeira/<AAAA>/
│   └── *_<AAAA>_<MM>.pdf                 boletim InfoBandeira do mês (GF_band, PLD mín/gatilho/máx, cor)
├── patamar/<AAAA>/
│   └── AAC001*.xlsx                      patamares de carga horários da CCEE do ano
├── ccee_newave/<AAAA>/<AAAA>_<MM>/       saídas e entradas do deck do NEWAVE da CCEE do mês
│   ├── ghtotsin.out, eafbm001…004.out
│   ├── cmarg001…004.out, cmarg001…004-med.out
│   └── sistema.dat, c_adic.dat
├── ecmwf_ena/
│   ├── ECENSLT_estat/ECENSLT<estat>_<abordagem>/                      média e percentis
│   │   └── ENA_MLT_SUBSISTEMA_MENSAL_ECENSLT<estat>_<abordagem>_…_<AAAAMMDD>.txt
│   └── ECENSLTm/<AAAA>-<MM>/                                          51 membros
│       └── ENA_MLT_SUBSISTEMA_MENSAL_ECENSLTm<NN>_…_<AAAAMMDD>.txt
└── bandeiras/historico.csv               histórico oficial da ANEEL (dados abertos)
```

Regras:
- **Deck do NEWAVE:** a pasta só é considerada se tiver `ghtotsin.out`. A versão é o hash do conteúdo:
  um deck republicado no mesmo mês entra como versão nova, ao lado da anterior.
- **ECMWF:** a data de emissão vem do fim do nome do arquivo (`_AAAAMMDD.txt`). Todas as emissões com data
  dentro do mês são ingeridas; uma emissão extra (ex.: dia 15) entra separada da do dia 1.
- **Patamares:** um arquivo por ano; se o ano ainda não foi publicado, a projeção usa o mesmo mês do ano
  anterior (D032).
- **Imutabilidade:** arquivo já ingerido e diferente do novo não é sobrescrito sem `--sobrescrever`
  (exceto o histórico da ANEEL, que é um conjunto atualizado pela fonte).
