// Conta da bandeira a partir de relatos do DECOMP (relato.rv0): a mesma de
// qe_forecast_bandeiras.relato (D034 do forecast-bandeiras-analytics). Roda no navegador (o usuário carrega
// os arquivos; nada sai do computador dele) e no teste de paridade Python × JS
// (tests/test_forecast_bandeiras_relato.py, com node).
//
// - PLD gatilho: do relato da CCEE (custo marginal por semana, patamar e submercado, limitado ao PLD mín/máx,
//   média do mês pelas horas de cada patamar, 4 submercados pela carga);
// - GH_band / GSF: do relato do ONS se informado; senão, do da CCEE (aproximação, até ~0,01 de GSF);
// - o CMO do relato do ONS nunca é usado como PLD. Sem GFOM.
//
// Interface sem DOM: `calcular(entrada)` recebe o texto dos relatos e devolve um objeto simples, para a
// página trocar esta conta por uma chamada ao servidor (FastAPI) sem mexer na interface.
(function (raiz) {
  const SUBS = ["SE", "S", "NE", "N"]; // ordem dos blocos do custo marginal; o 5º (FC) não entra
  const num = (s) => { const v = parseFloat(s); return Number.isNaN(v) ? 0 : v; };
  const linhasDe = (texto) => texto.split(/\r?\n/);
  const primeiro = (ln) => ln.trim().split(/\s+/)[0];

  // --- leitura do relato -----------------------------------------------------------------------------

  // Custo marginal: { SE: [[pat1 por semana], [pat2...], [pat3...]], S: ..., NE: ..., N: ..., FC: ... }
  function lerCmo(linhas) {
    const inicio = linhas.findIndex((l) => l.includes("CUSTO MARGINAL DE OPERACAO"));
    if (inicio < 0) throw new Error("bloco 'CUSTO MARGINAL DE OPERACAO' não encontrado no relato");
    const saida = {}; let atual = [], bordas = 0;
    for (let i = inicio; i < linhas.length; i++) {
      const p = linhas[i].trim().split(/\s+/);
      if (!p[0]) continue;
      if (p[0].startsWith("X-")) { if (++bordas === 3) break; continue; } // 2 do cabeçalho + 1 de fechamento
      if (p[0].startsWith("Pat_")) atual.push(p.slice(1).map(num));
      else if (p[0].startsWith("Med_")) { saida[p[0].slice(4)] = atual; atual = []; }
    }
    const faltam = SUBS.filter((s) => !saida[s]);
    if (faltam.length) throw new Error("custo marginal sem os submercados " + faltam.join(", "));
    return saida;
  }

  const NOMES_BALANCO = { Mercado: "mercado", PQUsi: "pqusi", Bacia: "pqusi", Cbomba: "cbomba", Ghid: "ghid",
    Gter: "gter", GterAT: "gterat", Geol: "geol" };

  // Balanço energético: uma linha por semana, subsistema e patamar (MWmed). Fica a primeira de cada chave.
  function lerBalanco(linhas, nSem) {
    const rows = [], vistos = new Set();
    let semana = null, sub = null, colunas = null;
    for (const ln of linhas) {
      let m = /SEMANA (\d) - ESTAGIO/.exec(ln); if (m) semana = parseInt(m[1], 10);
      m = /^\s+Subsistema (\w+)\s*$/.exec(ln); if (m) sub = m[1];
      if (primeiro(ln) === "Mercado") {
        const cab = ln.trim().split(/\s+/); colunas = cab.slice(0, cab.indexOf("Interligacao")); continue;
      }
      m = /^\s+Pat_(\d)\s+(.*)/.exec(ln);
      if (m && semana && sub && colunas) {
        const v = m[2].trim().split(/\s+/).slice(0, colunas.length).map(num);
        const linha = { semana, subsistema: sub, pat: parseInt(m[1], 10), it60: 0 };
        colunas.forEach((c, k) => { if (NOMES_BALANCO[c] && k < v.length) linha[NOMES_BALANCO[c]] = v[k]; });
        if (sub === "SE") { const t = ln.trim().split(/\s+/); linha.it60 = num(t[t.length - 1]); }
        const chave = semana + "|" + sub + "|" + linha.pat;
        if (!vistos.has(chave)) { vistos.add(chave); rows.push(linha); }
      }
    }
    return rows.filter((r) => r.semana <= nSem);
  }

  // Pequenas usinas: { tipo (PCH, PCT, EOL, UFV, ...gd), subsistema, semana, pat, mw }
  const SUB_PEQ = { SECO: "SE", SUL: "S", NE: "NE", N: "N" };
  function lerPequenas(linhas, nSem) {
    const ini = linhas.findIndex((l) => l.trim() === "Relatorio dos Dados de Pequenas Usinas");
    if (ini < 0) throw new Error("bloco de pequenas usinas não encontrado no relato");
    const saida = []; let usina = null, bordas = 0;
    for (let i = ini + 1; i < linhas.length; i++) {
      const ln = linhas[i];
      if (ln.trim().startsWith("X-")) { if (++bordas === 3) break; continue; }
      let estagio, valores, m = /^\s+(SECO|SUL|NE|N)_(PCH|PCT|EOL|UFV)(gd)?\s+\w+\s+(\d+)\s+(.*)/.exec(ln);
      if (m) { usina = { tipo: m[2] + (m[3] || ""), sub: SUB_PEQ[m[1]] }; estagio = parseInt(m[4], 10); valores = m[5].trim().split(/\s+/); }
      else {
        m = /^\s+(\d+)\s+([\d.]+\s.*)/.exec(ln);
        if (!m || !usina) continue;
        estagio = parseInt(m[1], 10); valores = m[2].trim().split(/\s+/);
      }
      if (estagio > nSem) continue;
      valores.slice(0, 3).forEach((v, k) => saida.push({ tipo: usina.tipo, subsistema: usina.sub, semana: estagio, pat: k + 1, mw: num(v) }));
    }
    return saida;
  }

  // ANDE (Itaipu para o Paraguai + consumo interno) por semana e patamar
  function lerAnde(linhas, nSem) {
    const ini = linhas.findIndex((l) => l.includes("Relatorio de eco  das informacoes de ITAIPU"));
    if (ini < 0) throw new Error("eco de Itaipu (ANDE) não encontrado no relato");
    const saida = [];
    for (let i = ini + 5; i < linhas.length; i++) {
      if (linhas[i].trim().startsWith("X-")) break;
      const t = linhas[i].trim().split(/\s+/);
      if (parseInt(t[0], 10) <= nSem) saida.push({ semana: parseInt(t[0], 10), pat: parseInt(t[1], 10), ande: num(t[t.length - 1]) });
    }
    return saida;
  }

  // Mês indicado no rótulo da semana 1 do relato ("OUTUBRO / SEMANA 1 - ESTAGIO 1"), de 1 a 12; null se não achar.
  // Só informativo: estudos customizados partem de um deck existente e o rótulo pode ficar igual.
  const MESES_RELATO = ["JANEIRO", "FEVEREIRO", "MARCO", "ABRIL", "MAIO", "JUNHO", "JULHO", "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"];
  function mesDoRelato(texto) {
    const m = /^\s*([A-Za-zÇç]+)\s*\/\s*SEMANA 1 - ESTAGIO/m.exec(texto);
    if (!m) return null;
    const nome = m[1].toUpperCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace("Ç", "C");
    const i = MESES_RELATO.indexOf(nome);
    return i < 0 ? null : i + 1;
  }

  // --- médias do mês ---------------------------------------------------------------------------------

  // Tabela patamar × semana de uma coluna (soma das linhas do mesmo patamar e semana).
  function tabelaPS(rows, coluna, horas) {
    const t = horas.map((l) => l.map(() => 0));
    for (const r of rows) if (r.pat >= 1 && r.pat <= horas.length && r.semana >= 1 && r.semana <= horas[0].length) t[r.pat - 1][r.semana - 1] += r[coluna] || 0;
    return t;
  }
  // Média ponderada pelas horas de uma tabela patamar × semana.
  function mediaPonderada(t, horas) {
    let s = 0, h = 0;
    for (let p = 0; p < horas.length; p++) for (let w = 0; w < horas[p].length; w++) { s += t[p][w] * horas[p][w]; h += horas[p][w]; }
    return s / h;
  }
  // Média mensal (MWmed) de uma coluna: soma por (pat, semana) e pondera pelas horas de `horas[pat][semana]`.
  function mediaMensal(rows, coluna, horas) { return mediaPonderada(tabelaPS(rows, coluna, horas), horas); }

  function fatoresVigentes(fatores, periodo) {
    const validos = Object.keys(fatores).filter((k) => k <= periodo).sort();
    if (!validos.length) throw new Error("sem fatores da CCEE para " + periodo);
    return fatores[validos[validos.length - 1]];
  }

  function ghBand(linhas, periodo, horas, fatores) {
    const nSem = horas[0].length, f = fatoresVigentes(fatores, periodo);
    const bal = lerBalanco(linhas, nSem);
    if (!bal.length) throw new Error("relato sem o balanço energético (é o relato completo?)");
    const ghOns = mediaMensal(bal, "ghid", horas) + mediaMensal(bal, "it60", horas);
    const ande = mediaMensal(lerAnde(linhas, nSem), "ande", horas);
    const pch = mediaMensal(lerPequenas(linhas, nSem).filter((r) => r.tipo === "PCH"), "mw", horas);
    const ghCg = (ghOns - ande) * (1 - f.perda_bruta_conexao) * (1 - f.perda_conexao_cg);
    const pchCg = pch * f.part_pch_mre * (1 - f.perda_pch_cg);
    return { gh_ons: ghOns, ande, pch_total: pch, gh_cg: ghCg, pch_cg: pchCg, gh_band: ghCg + pchCg };
  }

  function cargaSubmercados(linhas, horas) {
    const bal = lerBalanco(linhas, horas[0].length);
    if (!bal.length) throw new Error("relato sem o balanço energético (é o relato completo?)");
    const c = {}; for (const s of SUBS) c[s] = mediaMensal(bal.filter((r) => r.subsistema === s), "mercado", horas);
    return c;
  }

  function pldGatilho(linhasCcee, horas, pldMin, pldMax, linhasCarga) {
    const nSem = horas[0].length, cmo = lerCmo(linhasCcee);
    let carga, avisos = [];
    try { carga = cargaSubmercados(linhasCcee, horas); }
    catch (e) {
      if (!linhasCarga) throw e;
      avisos.push("relato da CCEE sem balanço: carga dos submercados tirada do relato do ONS");
      carga = cargaSubmercados(linhasCarga, horas);
    }
    const total = SUBS.reduce((a, s) => a + carga[s], 0), porSub = {};
    let h = 0; horas.forEach((l) => l.forEach((x) => { h += x; }));
    for (const s of SUBS) {
      if (cmo[s][0].length < nSem) throw new Error(s + ": custo marginal com " + cmo[s][0].length + " semanas, o mês tem " + nSem);
      let acc = 0;
      for (let p = 0; p < horas.length; p++) for (let w = 0; w < nSem; w++) acc += Math.min(Math.max(cmo[s][p][w], pldMin), pldMax) * horas[p][w];
      porSub[s] = acc / h;
    }
    return { pld_gatilho: SUBS.reduce((a, s) => a + porSub[s] * carga[s] / total, 0), pld_submercado: porSub, avisos };
  }

  // --- regra da bandeira -----------------------------------------------------------------------------

  const gsfBand = (gh, gf) => Number((gh / gf).toFixed(2)); // 2 casas, como pede a ANEEL

  function corBandeira(gsf, pld, limites) {
    const x = pld * Math.max(0, 1 - gsf);
    for (const [cor, lim] of Object.entries(limites)) if (x <= lim) return cor;
    return "Vermelha 2";
  }

  function folga(x, gsf, pld, limites) {
    let inf = 0, sup = Infinity;
    for (const lim of Object.values(limites)) { if (x <= lim) { sup = lim; break; } inf = lim; }
    return {
      x_limite_inferior: inf, x_limite_superior: sup,
      folga_para_cor_acima_x: sup - x, folga_para_cor_abaixo_x: x - inf,
      pld_cor_acima: gsf < 1 ? sup / (1 - gsf) : NaN,
      gsf_cor_acima: Number.isFinite(sup) && pld ? 1 - sup / pld : NaN,
    };
  }

  // GF_band e PLD mín/máx do último boletim até o mês (até 36 meses para trás); null se não houver.
  function valoresPublicados(boletim, periodo) {
    const [a, m] = periodo.split("-").map(Number), limite = a * 12 + m - 1 - 36;
    const meses = Object.keys(boletim).filter((k) => {
      const [ka, km] = k.split("-").map(Number), n = ka * 12 + km - 1;
      return k <= periodo && n >= limite && boletim[k].gf_band != null && boletim[k].pld_min != null;
    }).sort();
    if (!meses.length) return null;
    const b = boletim[meses[meses.length - 1]];
    return { gf_band: b.gf_band, pld_min: b.pld_min, pld_max: b.pld_max, origem: meses[meses.length - 1] };
  }

  // entrada: { periodo: "AAAA-MM", horas: [[pesado por semana], [médio], [leve]], fatores, limites_x,
  //            ccee: texto do relato da CCEE | null, ons: texto do relato do ONS | null,
  //            gf_band, pld_min, pld_max, pld_gatilho_manual (opcional) }
  function calcular(e) {
    if (!e.ccee && !e.ons) throw new Error("informe ao menos um relato (CCEE e/ou ONS)");
    if (!e.ccee && e.pld_gatilho_manual == null)
      throw new Error("só com o relato do ONS é preciso informar o PLD gatilho (o CMO do ONS não é o PLD gatilho)");
    const lCcee = e.ccee ? linhasDe(e.ccee) : null, lOns = e.ons ? linhasDe(e.ons) : null;
    const gh = ghBand(lOns || lCcee, e.periodo, e.horas, e.fatores);
    const gsf = gsfBand(gh.gh_band, e.gf_band);
    let pld, porSub = {}, fontePld, avisos = [];
    if (e.pld_gatilho_manual != null) { pld = e.pld_gatilho_manual; fontePld = "manual"; }
    else {
      const r = pldGatilho(lCcee, e.horas, e.pld_min, e.pld_max, lOns);
      pld = r.pld_gatilho; porSub = r.pld_submercado; fontePld = "CCEE"; avisos = r.avisos;
    }
    const x = pld * Math.max(0, 1 - gsf);
    return {
      mes: e.periodo, gh_band: gh.gh_band, gf_band: e.gf_band, gsf, pld_gatilho: pld, pld_submercado: porSub, x,
      cor: corBandeira(gsf, pld, e.limites_x), ...folga(x, gsf, pld, e.limites_x),
      fontes: { gh: lOns ? "ONS" : "CCEE (aproximação)", pld: fontePld }, avisos,
    };
  }


  // --- memória de cálculo ----------------------------------------------------------------------------
  // Os mesmos números de `calcular`, com cada passo intermediário, para o usuário conferir à mão.
  // Mesma entrada de `calcular`; devolve { horas, gh, pld, bandeira } (tabelas patamar × semana em MWmed ou R$/MWh).
  function memoria(e) {
    const lCcee = e.ccee ? linhasDe(e.ccee) : null, lOns = e.ons ? linhasDe(e.ons) : null;
    const fonteGh = lOns || lCcee, nSem = e.horas[0].length;
    const horasTotal = e.horas.reduce((a, l) => a + l.reduce((b, x) => b + x, 0), 0);
    const bal = lerBalanco(fonteGh, nSem);
    const peq = lerPequenas(fonteGh, nSem).filter((r) => r.tipo === "PCH");
    const ande = lerAnde(fonteGh, nSem);
    const chaveF = Object.keys(e.fatores).filter((k) => k <= e.periodo).sort().pop(), f = e.fatores[chaveF];
    const tGhid = tabelaPS(bal, "ghid", e.horas), tIt = tabelaPS(bal, "it60", e.horas);
    const tGh = tGhid.map((l, p) => l.map((v, w) => v + tIt[p][w]));
    const tAnde = tabelaPS(ande, "ande", e.horas), tPch = tabelaPS(peq, "mw", e.horas);
    const ghOns = mediaPonderada(tGh, e.horas), andeM = mediaPonderada(tAnde, e.horas), pchM = mediaPonderada(tPch, e.horas);
    const ghCg = (ghOns - andeM) * (1 - f.perda_bruta_conexao) * (1 - f.perda_conexao_cg);
    const pchCg = pchM * f.part_pch_mre * (1 - f.perda_pch_cg), ghBandV = ghCg + pchCg;
    const gsfBruto = ghBandV / e.gf_band, gsf = gsfBand(ghBandV, e.gf_band);
    const gh = { fonte: lOns ? "ONS" : "CCEE (aproximação)", tab_ghid: tGhid, tab_it60: tIt, tab_gh_ons: tGh, gh_ons: ghOns,
      tab_ande: tAnde, ande: andeM, tab_pch: tPch, pch: pchM, fatores: { ...f, vigente_desde: chaveF },
      gh_cg: ghCg, pch_cg: pchCg, gh_band: ghBandV, gf_band: e.gf_band, gsf_bruto: gsfBruto, gsf };
    let pld = null, pldV;
    if (e.pld_gatilho_manual != null) { pldV = e.pld_gatilho_manual; pld = { fonte: "manual", pld_gatilho: pldV }; }
    else {
      const cmo = lerCmo(lCcee); let carga, fonteCarga = "CCEE";
      try { carga = cargaSubmercados(lCcee, e.horas); } catch (err) { if (!lOns) throw err; carga = cargaSubmercados(lOns, e.horas); fonteCarga = "ONS"; }
      const total = SUBS.reduce((a, s) => a + carga[s], 0), subs = {};
      for (const s of SUBS) {
        const bruto = cmo[s].map((l) => l.slice(0, nSem));
        const limitado = bruto.map((l) => l.map((v) => Math.min(Math.max(v, e.pld_min), e.pld_max)));
        const medio = mediaPonderada(limitado, e.horas);
        subs[s] = { cmo: bruto, limitado, medio, carga: carga[s], peso: carga[s] / total, contribuicao: medio * carga[s] / total };
      }
      pldV = SUBS.reduce((a, s) => a + subs[s].contribuicao, 0);
      pld = { fonte: "CCEE", fonte_carga: fonteCarga, submercados: subs, carga_total: total, pld_min: e.pld_min, pld_max: e.pld_max, pld_gatilho: pldV };
    }
    const x = pldV * Math.max(0, 1 - gsf);
    return { periodo: e.periodo, horas: { tab: e.horas, total: horasTotal }, gh, pld,
      bandeira: { x, limites: e.limites_x, cor: corBandeira(gsf, pldV, e.limites_x), gsf, pld_gatilho: pldV } };
  }

  // Memória de cálculo em CSV (formato longo: secao;item;patamar;semana;valor), para abrir no Excel.
  const PAT = ["Pesado", "Médio", "Leve"];
  function memoriaCsv(m) {
    const L = [["secao", "item", "patamar", "semana", "valor"]];
    const tab = (secao, item, t) => t.forEach((l, p) => l.forEach((v, w) => L.push([secao, item, PAT[p], w + 1, v])));
    const esc = (c) => { const x = String(c); return /[;"\n]/.test(x) ? '"' + x.replace(/"/g, '""') + '"' : x; };
    tab("horas", "horas por patamar e semana", m.horas.tab); L.push(["horas", "total do mês", "", "", m.horas.total]);
    const g = m.gh;
    L.push(["gh_band", "fonte", "", "", g.fonte]);
    tab("gh_band", "Ghid (soma dos subsistemas)", g.tab_ghid); tab("gh_band", "Itaipu 60 Hz", g.tab_it60); tab("gh_band", "GH ONS = Ghid + Itaipu 60 Hz", g.tab_gh_ons);
    tab("gh_band", "ANDE", g.tab_ande); tab("gh_band", "PCH", g.tab_pch);
    for (const [k, v] of Object.entries({ gh_ons: g.gh_ons, ande: g.ande, pch: g.pch, gh_cg: g.gh_cg, pch_cg: g.pch_cg, gh_band: g.gh_band, gf_band: g.gf_band, gsf_sem_arredondar: g.gsf_bruto, gsf: g.gsf, ...g.fatores }))
      L.push(["gh_band", k, "", "", v]);
    const p = m.pld;
    L.push(["pld_gatilho", "fonte", "", "", p.fonte]);
    if (p.submercados) {
      L.push(["pld_gatilho", "pld_min", "", "", p.pld_min], ["pld_gatilho", "pld_max", "", "", p.pld_max]);
      for (const s of SUBS) {
        const d = p.submercados[s];
        tab("pld_gatilho", "CMO " + s, d.cmo); tab("pld_gatilho", "CMO limitado " + s, d.limitado);
        L.push(["pld_gatilho", "PLD médio " + s, "", "", d.medio], ["pld_gatilho", "carga média " + s, "", "", d.carga], ["pld_gatilho", "peso " + s, "", "", d.peso], ["pld_gatilho", "contribuição " + s, "", "", d.contribuicao]);
      }
    }
    L.push(["pld_gatilho", "pld_gatilho", "", "", p.pld_gatilho]);
    const b = m.bandeira;
    L.push(["bandeira", "x = pld x (1 - gsf)", "", "", b.x], ["bandeira", "cor", "", "", b.cor]);
    for (const [c, lim] of Object.entries(b.limites)) L.push(["bandeira", "limite de X até " + c, "", "", lim]);
    return "\uFEFF" + L.map((r) => r.map(esc).join(";")).join("\n");
  }

  // Fração das execuções em cada cor (peso igual).
  function probabilidadeCores(cores, ordem) {
    const p = {}; for (const c of ordem) p[c] = cores.filter((x) => x === c).length / cores.length;
    return p;
  }

  const api = { calcular, memoria, memoriaCsv, probabilidadeCores, valoresPublicados, mesDoRelato, lerCmo, lerBalanco, lerPequenas, lerAnde,
    mediaMensal, ghBand, pldGatilho, gsfBand, corBandeira };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.ContaRelato = api;
})(this);
