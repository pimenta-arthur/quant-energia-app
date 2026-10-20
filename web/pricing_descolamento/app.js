// Página do descolamento NE e N (portada de pricing-descolamento-analytics, web/descolamento/index.html).
// Dados: serving/pricing_descolamento/<chave>.json (qe_pricing_descolamento.publicacao). A conta que depende da curva
// do SE digitada está em descolamento_conta.js (paridade com o Python); o resto vem pronto do Python.
"use strict";
(async function () {
  const CHAVES = ["meta", "sazonal_se", "meses", "historico_periodos", "fund_periodos"];
  const D = {};
  try {
    await Promise.all(CHAVES.map(async k => {
      const r = await fetch(`/dados/pricing_descolamento/${k}.json`, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${k}: ${r.status}`);
      D[k] = await r.json();
    }));
  } catch (e) {
    const el = document.getElementById("erro"); el.hidden = false;
    el.textContent = `Dados da página indisponíveis (${e.message}). Rode: uv run qe pricing_descolamento publicar`;
    return;
  }

  // ---------------------------------------------------------------- dados e utilidades
  const M = D.meses, SAZ = D.sazonal_se.fator, meta = D.meta;
  const CONTA = window.ContaDescolamento.criar(M, SAZ);
  const IDX = CONTA.IDX, ANOS = CONTA.ANOS, horas = CONTA.horas;
  const ano = p => +p.slice(0, 4);
  const dn = (v, c = 1) => (v == null || !isFinite(v) ? "—" : (v < -0.5 * 10 ** -c ? "−" : "") + n(Math.abs(v), c));
  const parseNum = s => { if (s == null) return null; s = String(s).trim().replace(/\s/g, "").replace(/R\$/i, ""); if (!s) return null;
    if (s.includes(",")) s = s.replace(/\./g, "").replace(",", "."); const v = Number(s); return isFinite(v) ? v : null; };
  // rótulos dos períodos de cada ano do horizonte
  const PER = CONTA.PER.map(a => {
    const yy = String(a.y).slice(2);
    return { ...a, rot: a.meses.length === 12 ? String(a.y) : `${rot(a.meses[0]).slice(0, 3)}–${rot(a.meses.at(-1))}`,
      S: a.S.map(s => ({ ...s, rot: `${s.s}º sem/${yy}` })), T: a.T.map(t => ({ ...t, rot: `T${t.t}/${yy}` })) };
  });
  function produtos(tipo) {
    const L = [];
    PER.forEach(a => {
      if (tipo === "ano") L.push({ rot: a.rot, meses: a.meses, parcial: a.meses.length < 12 });
      if (tipo === "sem") a.S.forEach(s => s.meses.length && L.push({ rot: s.rot, meses: s.meses, parcial: s.meses.length < 6 }));
      if (tipo === "tri") a.T.forEach(t => t.meses.length && L.push({ rot: t.rot, meses: t.meses, parcial: t.meses.length < 3 }));
      if (tipo === "mes") a.meses.forEach(p => L.push({ rot: rot(p), meses: [p], parcial: false }));
    });
    return L;
  }
  function rotuloChave(k) {
    if (k[0] === "A") return k.slice(1); if (k[0] === "M") return rot(k.slice(1));
    const [y, i] = k.slice(1).split("-"); return k[0] === "S" ? `${i}º sem/${y.slice(2)}` : `T${i}/${y.slice(2)}`;
  }

  // ---------------------------------------------------------------- estado da curva (persistido no navegador)
  let ENT = {}, SAZMODO = "plana";
  // a página abre vazia: o usuário informa a curva (chave v2 ignora curvas salvas antes desta mudança)
  try { const s = JSON.parse(localStorage.getItem("descolamento.curva.v2") || "null"); if (s) { ENT = s.ent || {}; SAZMODO = s.saz || "plana"; } } catch (e) {}
  const salvar = () => { try { localStorage.setItem("descolamento.curva.v2", JSON.stringify({ ent: ENT, saz: SAZMODO })); } catch (e) {} };
  const resolver = () => CONTA.resolver(ENT, SAZMODO);
  const textoAviso = a => a.tipo === "media"
    ? `${rotuloChave(a.chave)}: os períodos informados dão média ${n(a.media, 1)}, diferente de ${n(a.v, 1)}.`
    : `${rot(a.mes)}: SE derivado de ${n(a.v, 1)} abaixo do piso (${n(a.piso, 2)}); descolamento zero.`;

  // ---------------------------------------------------------------- tabela de entrada
  const MESES_ABR = MES;
  const ABERTOS = new Set();
  function desenharCurva() {
    const t = document.getElementById("curva");
    let h = `<thead><tr><th>Ano</th><th>Ano</th><th>1º sem</th><th>2º sem</th><th>T1</th><th>T2</th><th>T3</th><th>T4</th><th>Meses</th></tr></thead><tbody>`;
    PER.forEach(a => {
      const inp = (k, ok) => `<td><input type="text" inputmode="decimal" data-k="${k}" ${ok ? "" : "disabled"} aria-label="SE ${rotuloChave(k)}"></td>`;
      h += `<tr data-ano="${a.y}"><td><b>${a.rot}</b></td>${inp(a.k, true)}${a.S.map(s => inp(s.k, s.meses.length)).join("")}${a.T.map(x => inp(x.k, x.meses.length)).join("")}` +
        `<td><button type="button" class="exp" data-ano="${a.y}" aria-expanded="${ABERTOS.has(a.y)}">${ABERTOS.has(a.y) ? "▾ ocultar" : "▸ abrir"}</button></td></tr>`;
      if (ABERTOS.has(a.y)) {
        h += `<tr class="meses-row"><td></td><td colspan="8"><div style="display:grid;grid-template-columns:repeat(12,minmax(58px,1fr));gap:4px">` +
          MESES_ABR.map((mm, i) => { const p = `${a.y}-${String(i + 1).padStart(2, "0")}`, ok = IDX[p] != null;
            return `<label><span class="mlbl">${mm}</span><input type="text" inputmode="decimal" data-k="M${p}" ${ok ? "" : "disabled"} aria-label="SE ${rot(p)}"></label>`; }).join("") + `</div></td></tr>`;
      }
    });
    t.innerHTML = h + "</tbody>";
    t.querySelectorAll(".exp").forEach(b => b.addEventListener("click", () => { const y = +b.dataset.ano; ABERTOS.has(y) ? ABERTOS.delete(y) : ABERTOS.add(y); desenharCurva(); atualizar(); }));
    t.querySelectorAll("input[data-k]").forEach(i => {
      i.addEventListener("change", () => { const v = parseNum(i.value); if (v == null) delete ENT[i.dataset.k]; else ENT[i.dataset.k] = v; salvar(); atualizar(); });
      i.addEventListener("paste", ev => {
        const txt = (ev.clipboardData || window.clipboardData).getData("text"); if (!/[\t\n]/.test(txt.trim())) return;
        ev.preventDefault();
        const vals = txt.trim().split(/[\t\n\r]+/).map(parseNum), todos = [...t.querySelectorAll("input[data-k]:not(:disabled)")];
        let j = todos.indexOf(i);
        vals.forEach(v => { const alvo = todos[j++]; if (!alvo) return; if (v == null) delete ENT[alvo.dataset.k]; else ENT[alvo.dataset.k] = v; });
        salvar(); atualizar();
      });
    });
  }
  function pintarCurva(r) {
    document.querySelectorAll("#curva input[data-k]").forEach(i => {
      const k = i.dataset.k, inf = r.info[k], dig = ENT[k] != null;
      if (document.activeElement !== i) i.value = dig ? n(ENT[k], 2).replace(/,00$/, "") : "";
      i.placeholder = !dig && inf && inf.v != null ? n(inf.v, 1) : "";
      i.classList.toggle("digitado", dig);
      i.classList.toggle("alerta", !!(inf && inf.v != null && inf.v < meta.piso));
    });
    const avisos = [...new Set(r.avisos.map(textoAviso))].slice(0, 6);
    document.getElementById("avisos-curva").innerHTML = avisos.map(a => `<span>⚠ ${a}</span>`).join("");
    document.getElementById("leg-curva").textContent = `Azul = digitado; cinza = derivado. Dentro de cada período sem preço próprio, a curva é ${SAZMODO === "hist" ? `distribuída pela sazonalidade média do SE (${D.sazonal_se.anos[0]}–${D.sazonal_se.anos.at(-1)}, instável entre anos)` : "plana"}. Piso ${meta.piso.toLocaleString("pt-BR")} e teto ${meta.teto.toLocaleString("pt-BR")} R$/MWh de ${meta.deck.slice(0, 4)} (usados no horizonte).`;
  }

  // ---------------------------------------------------------------- resultado
  let SUB = "NE", MODO = "d", PROD = "ano", RES = {};
  const agregar = ms => CONTA.agregar(RES, ms);
  // detalhe do preço justo por ano climático (cada cenário agregado no período, ponderado por horas)
  function detalheAnos(ms) {
    const pld = MODO === "pld", linhas = CONTA.porAno(RES, ms, SUB, pld);
    const comp = linhas.filter(l => !l.parcial), vs = comp.map(l => l.v);
    const mais = Math.min(...vs), menos = Math.max(...vs);
    const g = agregar(ms), justo = (pld ? g.se : 0) + g[SUB];
    const fmt = v => pld ? n(v, 1) : dn(v);
    let h = `<div style="margin-top:6px;padding-top:6px;border-top:1px solid color-mix(in srgb, var(--bg) 35%, transparent)">Por ano climático (${SUB}${pld ? ", PLD implícito" : ""})</div>`;
    h += `<table style="border-collapse:collapse;font:inherit;color:inherit;background:none">` + linhas.map(l => {
      const nota = l.parcial ? ` <span style="opacity:.7">parcial (${rot(l.meses[0])}${l.meses.length > 1 ? "–" + rot(l.meses.at(-1)) : ""})</span>` :
        comp.length > 1 && l.v === mais ? ` <span style="opacity:.7">← mais descolado</span>` : comp.length > 1 && l.v === menos ? ` <span style="opacity:.7">← menos descolado</span>` : "";
      return `<tr><td style="padding:0 10px 0 0;border:0">${l.ano}</td><td style="padding:0;border:0;text-align:right;font-family:var(--f-data)">${fmt(l.v)}</td><td style="padding:0 0 0 6px;border:0">${nota}</td></tr>`;
    }).join("") + `<tr><td style="padding:2px 10px 0 0;border:0"><b>preço justo</b></td><td style="padding:2px 0 0;border:0;text-align:right;font-family:var(--f-data)"><b>${fmt(justo)}</b></td><td style="border:0"></td></tr></table>`;
    h += `<div style="opacity:.7;margin-top:4px">Cada ano traz vento, sol, hidrologia e o k observado nele.${linhas.some(l => l.parcial) ? " O justo é calculado mês a mês; o ano parcial entra só nos meses que tem." : ""}</div>`;
    return h;
  }
  const ABERTOS_RES = new Set();
  function resumo() {
    const pld = MODO === "pld";
    document.getElementById("tt-res").textContent = `${pld ? "PLD implícito" : "Descolamento"} do ${SUB} por produto, R$/MWh`;
    const cel = (ms, cls = "") => {
      const g = ms.length ? agregar(ms) : null;
      if (!ms.length) return `<td class="${cls}"></td>`;
      if (!g) return `<td class="${cls}"><div class="cel vazio">—</div></td>`;
      const base = pld ? g.se : 0, fx = g[SUB + "min"] != null ? `<span class="fx">${dn(base + g[SUB + "min"])} a ${dn(base + g[SUB + "max"])}</span>` : "";
      return `<td class="${cls}"><div class="cel" data-dica="${ms[0]}|${ms.at(-1)}"><b>${pld ? n(base + g[SUB], 1) : dn(g[SUB])}</b>${fx}</div></td>`;
    };
    let h = `<thead><tr><th>Ano</th><th>Ano</th><th>1º sem</th><th>2º sem</th><th>T1</th><th>T2</th><th>T3</th><th>T4</th><th>Meses</th></tr></thead><tbody>`;
    PER.forEach(a => {
      h += `<tr><td><b>${a.rot}</b></td>${cel(a.meses, "ano-res")}${a.S.map(x => cel(x.meses)).join("")}${a.T.map(x => cel(x.meses)).join("")}` +
        `<td><button type="button" class="exp" data-ano="${a.y}" aria-expanded="${ABERTOS_RES.has(a.y)}">${ABERTOS_RES.has(a.y) ? "▾ ocultar" : "▸ abrir"}</button></td></tr>`;
      if (ABERTOS_RES.has(a.y)) {
        h += `<tr class="meses-row"><td></td><td colspan="8"><div style="display:grid;grid-template-columns:repeat(12,minmax(58px,1fr));gap:4px">` +
          MESES_ABR.map((mm, i) => { const p = `${a.y}-${String(i + 1).padStart(2, "0")}`; const ok = IDX[p] != null;
            return `<div><span class="mlbl">${mm}</span>${ok ? cel([p]).replace(/^<td[^>]*>|<\/td>$/g, "") : ""}</div>`; }).join("") + `</div></td></tr>`;
      }
    });
    const t = document.getElementById("resumo");
    if (!Object.keys(RES).length) h += `<tr><td colspan="9" class="vazio-msg">Informe a curva do Sudeste acima para ver o descolamento por produto.</td></tr>`;
    t.innerHTML = h + "</tbody>";
    t.querySelectorAll(".exp").forEach(b => b.addEventListener("click", () => { const y = +b.dataset.ano; ABERTOS_RES.has(y) ? ABERTOS_RES.delete(y) : ABERTOS_RES.add(y); resumo(); }));
    t.querySelectorAll(".cel[data-dica]").forEach(c => {
      const [p0, p1] = c.dataset.dica.split("|"), ms = M.map(m => m.mes).filter(p => p >= p0 && p <= p1), g = agregar(ms);
      dicaEm(c, `<b>${p0 === p1 ? rot(p0) : rot(p0) + " a " + rot(p1)}</b> · SE ${n(g.se, 1)}<br>NE ${dn(g.NE)} · N ${dn(g.N)}<br>PLD NE ${n(g.se + g.NE, 1)} · PLD N ${n(g.se + g.N, 1)}` + detalheAnos(ms));
    });
  }
  // fundamentos por mês (modelo e realizado, com sobra e folga) prontos do Python
  const FUNDM = Object.fromEntries(D.fund_periodos.serie.map(x => [x.mes, x]));
  function grafico() {
    const svg = document.getElementById("g-mes"), w = 1040, h = 280, mg = { l: 48, r: 12, t: 14, b: 28 };
    svg.replaceChildren();
    const ms = M.map(m => m.mes).filter(p => RES[p]);
    const pld = MODO === "pld";
    document.getElementById("tt-graf").textContent = `${pld ? "PLD implícito" : "Descolamento"} do ${SUB} por mês, R$/MWh`;
    document.getElementById("leg-graf").innerHTML = pld
      ? `<span><i class="l" style="border-color:var(--accent)"></i>PLD ${SUB} justo</span><span><i style="background:var(--faixa-proj)"></i>Faixa entre cenários</span><span><i class="l" style="border-color:var(--ink-3)"></i>SE informado</span><span><i class="t" style="border-color:var(--ink-3)"></i>Piso</span>`
      : `<span><i class="l" style="border-color:var(--accent)"></i>Preço justo</span><span><i style="background:var(--faixa-proj)"></i>Faixa entre cenários (mín–máx)</span>`;
    document.getElementById("leg-g").textContent = pld ? "PLD implícito = SE informado + descolamento. Piso do ano do deck." : "Média ponderada dos cenários climáticos; faixa = cenário mais e menos descolado em cada mês.";
    if (!ms.length) { S(svg, "text", { x: w / 2, y: h / 2, "text-anchor": "middle" }, "Informe a curva do Sudeste acima"); return; }
    const val = p => pld ? RES[p].se + RES[p][SUB] : RES[p][SUB];
    const lo = p => (pld ? RES[p].se : 0) + RES[p][SUB + "min"], hi = p => (pld ? RES[p].se : 0) + RES[p][SUB + "max"];
    let vals = ms.flatMap(p => [lo(p), hi(p), val(p)]); if (pld) vals = vals.concat(ms.map(p => RES[p].se), [M[0].piso]); else vals.push(0);
    const e = eixo(Math.min(...vals), Math.max(...vals), 5);
    const X = i => mg.l + (ms.length === 1 ? 0.5 : i / (ms.length - 1)) * (w - mg.l - mg.r), Y = v => mg.t + (h - mg.t - mg.b) * (1 - (v - e.a) / (e.b - e.a));
    e.t.forEach(t => { S(svg, "line", { x1: mg.l, x2: w - mg.r, y1: Y(t), y2: Y(t), stroke: "var(--rule)" }); S(svg, "text", { x: mg.l - 6, y: Y(t) + 3, "text-anchor": "end" }, n(t)); });
    S(svg, "polygon", { points: [...ms.map((p, i) => `${X(i)},${Y(hi(p))}`), ...ms.map((p, i) => `${X(i)},${Y(lo(p))}`).reverse()].join(" "), fill: "var(--faixa-proj)" });
    if (pld) {
      S(svg, "line", { x1: mg.l, x2: w - mg.r, y1: Y(M[0].piso), y2: Y(M[0].piso), stroke: "var(--ink-3)", "stroke-dasharray": "4 3" });
      S(svg, "polyline", { points: ms.map((p, i) => `${X(i)},${Y(RES[p].se)}`).join(" "), fill: "none", stroke: "var(--ink-3)", "stroke-width": 1.4 });
    } else S(svg, "line", { x1: mg.l, x2: w - mg.r, y1: Y(0), y2: Y(0), stroke: "var(--ink-3)" });
    S(svg, "polyline", { points: ms.map((p, i) => `${X(i)},${Y(val(p))}`).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 2.2 });
    ms.forEach((p, i) => {
      if (rotuloDeMes(p) || (i === 0 && !ms.slice(1, 3).some(rotuloDeMes))) S(svg, "text", { x: X(i), y: h - 8, "text-anchor": "middle" }, rot(p));
      const r = RES[p], dx = (w - mg.l - mg.r) / Math.max(ms.length - 1, 1);
      const alvo = S(svg, "rect", { x: X(i) - dx / 2, y: mg.t, width: dx, height: h - mg.t - mg.b, fill: "transparent" });
      dicaEm(alvo, () => {
        // mês a mês: o porquê do ponto (física do NE), o mesmo mês realizado e os anos que formam a faixa
        const fm = FUNDM[p].mod, re = M[IDX[p]].real, base = pld ? r.se : 0, fmt = v => pld ? n(v, 1) : dn(v);
        const ext = [...r.cen].sort((a, b) => a[SUB] - b[SUB]);
        let t = `<b>${rot(p)}</b> · SE ${n(r.se, 1)}<br>${pld ? "PLD " : ""}${SUB} ${fmt(base + r[SUB])} · faixa ${fmt(base + r[SUB + "min"])} a ${fmt(base + r[SUB + "max"])}`;
        // 1º semestre: trava o tronco N/NE→SE (sobra N+NE); 2º semestre: trava o limite de exportação do NE
        t += +p.slice(5, 7) <= 6
          ? `<br>Por quê (NE): trava ${pct(r.trava)} das horas · k ${n(fm.k, 2)}<br>sobra NE ${dn(fm.sobra)} GW · hidráulica N ${n(fm.hidr_N, 1)} GW`
          : `<br>Por quê (NE): trava ${pct(r.trava)} das horas · k ${n(fm.k, 2)}<br>folga até o limite ${n(fm.folga, 1)} GW`;
        if (re && re.se != null && re["d_" + SUB] != null)
          t += `<br>Realizado ${rot(re.mes)}: SE ${n(re.se, 1)} · ${pld ? "PLD " + SUB + " " + n(re.se + re["d_" + SUB], 1) : SUB + " " + dn(re["d_" + SUB])}`;
        if (ext.length > 1) t += `<br>Extremos: mais descolado ${ext[0].id} · menos ${ext.at(-1).id}`;
        return t;
      });
    });
  }
  function tabela() {
    const L = produtos(PROD).map(p => ({ ...p, g: agregar(p.meses) }));
    const fx = (g, s) => g && g[s + "min"] != null ? `<span class="fx">${dn(g[s + "min"])} a ${dn(g[s + "max"])}</span>` : "";
    if (!Object.keys(RES).length) { document.getElementById("tab-prod").innerHTML = `<tr><td colspan="7" class="vazio-msg">Informe a curva do Sudeste acima.</td></tr>`; return; }
    document.getElementById("tab-prod").innerHTML = L.map(({ rot: r, g, parcial }) => g
      ? `<tr class="${parcial ? "parcial" : ""}"><td>${r}</td><td class="n">${n(g.se, 1)}</td><td class="n"><b>${dn(g.NE)}</b>${fx(g, "NE")}</td><td class="n"><b>${dn(g.N)}</b>${fx(g, "N")}</td>` +
        `<td class="n">${n(g.se + g.NE, 1)}</td><td class="n">${n(g.se + g.N, 1)}</td><td class="n">${pct(g.trava)}</td></tr>`
      : `<tr><td>${r}</td><td class="n" colspan="6">informe o SE</td></tr>`).join("");
  }
  function copiar(txt, id) {
    const ok = m => { const e = document.getElementById(id); e.textContent = m; setTimeout(() => { e.textContent = ""; }, 4000); };
    const plano = () => { const t = document.createElement("textarea"); t.value = txt; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); ok("Tabela copiada"); } catch (e) { ok("Selecione e copie manualmente"); } t.remove(); };
    try { navigator.clipboard.writeText(txt).then(() => ok("Tabela copiada; cole no Excel"), plano); } catch (e) { plano(); }
  }
  function csv() {
    // copia a tabela no formato do Excel (tabulação e vírgula decimal)
    const L = produtos(PROD).map(p => ({ ...p, g: agregar(p.meses) })).filter(p => p.g);
    const c = v => (v == null || !isFinite(v) ? "" : v.toFixed(2).replace(".", ","));
    copiar([["periodo", "SE", "NE_justo", "NE_min", "NE_max", "N_justo", "N_min", "N_max", "PLD_NE", "PLD_N", "horas_travadas_NE"].join("\t"),
      ...L.map(({ rot: r, g }) => [r, c(g.se), c(g.NE), c(g.NEmin), c(g.NEmax), c(g.N), c(g.Nmin), c(g.Nmax), c(g.se + g.NE), c(g.se + g.N), c(g.trava)].join("\t"))].join("\n"), "copiado");
  }

  // ---------------------------------------------------------------- fundamentos do deck (prontos do Python)
  const FUND = [
    ["renov_NE", "Renovável do NE", "GW", 1], ["carga_NE", "Carga do NE", "GW", 1], ["carga_N", "Carga do N", "GW", 1],
    ["hidr_N", "Hidráulica do N", "GW", 1], ["sobra", "Sobra renovável do NE (renov. − carga)", "GW", 1],
    ["lim_NE", "Limite de exportação do NE", "GW", 1], ["folga", "Folga até o limite de exportação", "GW", 1],
    ["trava", "Horas travadas do NE (chance média)", "%", 100], ["k", "Intensidade k do NE (quando trava)", "", 1],
  ];
  function fundamentos() {
    const box = document.getElementById("mult"); box.replaceChildren();
    const serie = D.fund_periodos.serie;
    FUND.forEach(([f, tit, un, esc]) => {
      const d = document.createElement("div"); d.className = "mini";
      d.innerHTML = `<div class="ttl">${tit}<span>${un}</span></div>`;
      const w = 300, h = 110, mg = { l: 30, r: 6, t: 6, b: 16 };
      const svg = S(d, "svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": tit });
      const ms = serie.map(x => x.mes), mod = serie.map(x => x.mod[f] * esc), rea = f === "k" ? serie.map(() => null) : serie.map(x => x.rea && x.rea[f] != null ? x.rea[f] * esc : null);
      const vs = [...mod, ...rea].filter(v => v != null && isFinite(v)); if (!vs.length) return;
      if (f === "sobra") vs.push(0);
      const e = eixo(Math.min(...vs), Math.max(...vs), 3);
      const X = i => mg.l + i / (ms.length - 1) * (w - mg.l - mg.r), Y = v => mg.t + (h - mg.t - mg.b) * (1 - (v - e.a) / (e.b - e.a));
      e.t.forEach(t => { S(svg, "line", { x1: mg.l, x2: w - mg.r, y1: Y(t), y2: Y(t), stroke: "var(--rule)" }); S(svg, "text", { x: mg.l - 4, y: Y(t) + 3, "text-anchor": "end" }, n(t, un === "" ? 1 : 0)); });
      S(svg, "polyline", { points: mod.map((v, i) => `${X(i)},${Y(v)}`).join(" "), fill: "none", stroke: "var(--accent)", "stroke-width": 1.8 });
      rea.forEach((v, i) => { if (v != null) S(svg, "circle", { cx: X(i), cy: Y(v), r: 1.8, fill: "var(--ink)" }); });
      ms.forEach((p, i) => {
        if (/-01$/.test(p)) S(svg, "text", { x: X(i), y: h - 3, "text-anchor": "middle" }, p.slice(2, 4));
        const alvo = S(svg, "rect", { x: X(i) - 3, y: mg.t, width: 6, height: h - mg.t - mg.b, fill: "transparent" });
        const r = serie[i].rea;
        dicaEm(alvo, `<b>${rot(p)}</b> · modelo ${n(mod[i], un === "" ? 2 : 1)} ${un}` + (r && rea[i] != null ? `<br>realizado ${rot(r.mes)}: ${n(rea[i], un === "" ? 2 : 1)} ${un}` : ""));
      });
      box.appendChild(d);
    });
  }
  let PFUND = "ano";
  const COLS_FUND = [["renov_NE", 1], ["carga_NE", 1], ["carga_N", 1], ["hidr_N", 1], ["sobra", 1], ["lim_NE", 1], ["folga", 1], ["trava", "%"], ["k", 2]];
  function tabelaFund() {
    const fmt = (v, c) => v == null ? "—" : c === "%" ? pct(v) : c === 2 ? n(v, 2) : (v < -0.05 ? "−" : "") + n(Math.abs(v), 1);
    document.getElementById("tab-fund").innerHTML = D.fund_periodos[PFUND].map(g => {
      const rs = g.refs, idx = p => +p.slice(0, 4) * 12 + +p.slice(5, 7);
      const continuo = rs.every((p, i) => i === 0 || idx(p) - idx(rs[i - 1]) === 1);
      const ref = !rs.length ? "" : rs.length === 1 ? rot(rs[0]) : continuo ? `${rot(rs[0])} a ${rot(rs.at(-1))}` : rs.map(rot).join(", ");
      return `<tr class="${g.parcial ? "parcial" : ""}"><td>${g.rot}${ref ? `<span class="fx">real: ${ref}</span>` : ""}</td>` +
        COLS_FUND.map(([f, c]) => `<td class="n"><b>${fmt(g.mod[f], c)}</b><span class="fx">${fmt(g.rea[f], c)}</span></td>`).join("") + "</tr>";
    }).join("");
  }
  function copiarFund() {
    const c = v => (v == null || !isFinite(v) ? "" : v.toFixed(3).replace(".", ","));
    const cab = ["periodo", ...COLS_FUND.flatMap(([f]) => [f + "_modelo", f + "_realizado"])].join("\t");
    copiar([cab, ...D.fund_periodos[PFUND].map(g => [g.rot, ...COLS_FUND.flatMap(([f]) => [c(g.mod[f]), c(g.rea[f])])].join("\t"))].join("\n"), "copiado-fund");
  }

  // ---------------------------------------------------------------- choque no SE
  let CHOQUE = 10, CHOQUE_UN = "rs";
  function sensibilidade(se) {
    const aj = CHOQUE_UN === "pct" ? x => x * (1 + CHOQUE / 100) : x => x + CHOQUE;
    const ch = CONTA.calcular(se, aj);
    if (!Object.keys(RES).length) { document.getElementById("tab-sens").innerHTML = `<tr><td colspan="9" class="vazio-msg">Informe a curva do Sudeste acima.</td></tr>`; return; }
    const anos = produtos("ano"), sems = produtos("sem");
    const L = anos.flatMap(a => [a, ...sems.filter(x => x.meses.every(p => a.meses.includes(p)) && x.meses.length < a.meses.length)]);
    document.getElementById("tab-sens").innerHTML = L.map(p => {
      const a = agregar(p.meses), b = CONTA.agregar(ch, p.meses);
      return a && b ? `<tr class="${p.parcial ? "parcial" : ""}"><td>${anos.includes(p) ? `<b>${p.rot}</b>` : `&nbsp;&nbsp;${p.rot}`}</td>` +
        `<td class="n delta"><b>${sn(b.NE - a.NE, 2)}</b></td><td class="n delta ult"><b>${sn(b.N - a.N, 2)}</b></td>` +
        `<td class="n">${n(a.se, 1)}</td><td class="n">${n(b.se, 1)}</td><td class="n">${dn(a.NE)}</td><td class="n">${dn(b.NE)}</td><td class="n">${dn(a.N)}</td><td class="n">${dn(b.N)}</td></tr>`
        : "";
    }).join("");
  }

  // ---------------------------------------------------------------- descolamento realizado (pronto do Python)
  const HP = D.historico_periodos, ABERTOS_HIST = new Set();
  function dicaHist(c) {
    const fmt = (v, t) => v == null ? "—" : t === "rs" ? dn(v) : t === "pct" ? pct(v) : t === "k" ? n(v, 2) : n(v, 1);
    const td = (x, al = "right") => `<td style="padding:1px 0 1px 10px;border:0;text-align:${al};font-family:var(--f-data)">${x}</td>`;
    const rotMed = `média ${c.rot.replace(/\/\d\d$/, "").replace(/ \d{4}$/, "")} ${c.anos[0]}–${String(c.anos.at(-1)).slice(2)}`;
    let h = `<b>${c.rot}</b> · SE ${n(c.SE, 1)}<table style="border-collapse:collapse;margin-top:4px;font:inherit;color:inherit;background:none">` +
      `<tr><td style="border:0"></td>${["valor", rotMed, "posição"].map(x => td(`<span style="opacity:.7">${x}</span>`)).join("")}</tr>`;
    c.linhas.forEach(l => {
      if (l === null) { h += `<tr><td colspan="4" style="border:0;padding:3px 0"><div style="border-top:1px solid color-mix(in srgb, var(--bg) 35%, transparent)"></div></td></tr>`; return; }
      let d = "—";
      if (l.v != null && l.med != null) {
        if (l.tipo === "pct") d = sn((l.v - l.med) * 100, 0) + " p.p.";
        else if (Math.abs(l.med) > 0.05) d = sn((l.v / l.med - 1) * 100, 0) + "%";
      }
      h += `<tr><td style="padding:1px 0;border:0">${l.nome}</td>${td(fmt(l.v, l.tipo))}${td(`${fmt(l.med, l.tipo)}${d !== "—" ? ` (${d})` : ""}`)}${td(l.pos == null ? "—" : `${l.pos}º/${l.n}`)}</tr>`;
    });
    h += `</table><div style="opacity:.7;margin-top:4px">Posição: 1º = mais descolado ou maior valor. % da folga = descolamento ÷ (SE − piso), só anos com SE acima do piso.` +
      (c.cob < 0.95 ? ` Física com ${pct(c.cob)} das horas do DESSEM no mês com menos dados.` : "") + `</div>`;
    return h;
  }
  function historicoReal() {
    const t = document.getElementById("hist-real"); if (!t || !HP.length) return;
    const pld = MODO === "pld";
    const CEL = [];
    const cel = (c, cls = "") => {
      if (!c) return `<td class="${cls}"></td>`;
      const v = c["d_" + SUB], m = c.marca[SUB];
      const marca = m ? ` <span class="marca-cel" title="${m === "▲" ? "mais descolado que a média" : "menos descolado que a média"}">${m}</span>` : "";
      CEL.push(c);
      return `<td class="${cls}"><div class="cel" data-i="${CEL.length - 1}"><b>${pld ? n(c.SE + v, 1) : dn(v)}</b>${marca}<span class="fx">SE ${n(c.SE)}</span></div></td>`;
    };
    let h = `<thead><tr><th>Ano</th><th>Ano</th><th>1º sem</th><th>2º sem</th><th>T1</th><th>T2</th><th>T3</th><th>T4</th><th>Meses</th></tr></thead><tbody>`;
    HP.forEach(a => {
      h += `<tr><td><b>${a.rot}</b></td>${cel(a.A, "ano-res")}${cel(a.S1)}${cel(a.S2)}${[1, 2, 3, 4].map(q => cel(a["T" + q])).join("")}` +
        `<td><button type="button" class="exp" data-ano="${a.ano}" aria-expanded="${ABERTOS_HIST.has(a.ano)}">${ABERTOS_HIST.has(a.ano) ? "▾ ocultar" : "▸ abrir"}</button></td></tr>`;
      if (ABERTOS_HIST.has(a.ano)) {
        h += `<tr class="meses-row"><td></td><td colspan="8"><div style="display:grid;grid-template-columns:repeat(12,minmax(58px,1fr));gap:4px">` +
          MESES_ABR.map((mm, i) => { const p = `${a.ano}-${String(i + 1).padStart(2, "0")}`, c = a.M[p];
            return `<div><span class="mlbl">${mm}</span>${c ? cel(c).replace(/^<td[^>]*>|<\/td>$/g, "") : ""}</div>`; }).join("") + `</div></td></tr>`;
      }
    });
    t.innerHTML = h + "</tbody>";
    t.querySelectorAll(".exp").forEach(b => b.addEventListener("click", () => { const y = +b.dataset.ano; ABERTOS_HIST.has(y) ? ABERTOS_HIST.delete(y) : ABERTOS_HIST.add(y); historicoReal(); }));
    t.querySelectorAll(".cel[data-i]").forEach(c => dicaEm(c, () => dicaHist(CEL[+c.dataset.i])));
  }

  // ---------------------------------------------------------------- orquestração
  function atualizar() {
    const r = resolver(); pintarCurva(r);
    RES = CONTA.calcular(r.se);
    resumo(); grafico(); tabela(); sensibilidade(r.se);
  }
  function abas(id, cb) {
    document.getElementById(id).addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return;
      document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute("aria-pressed", String(x === b))); cb(b.dataset.v); });
  }
  abas("abas-sub", v => { SUB = v; resumo(); grafico(); historicoReal(); });
  abas("abas-modo", v => { MODO = v; resumo(); grafico(); historicoReal(); });
  abas("abas-prod", v => { PROD = v; tabela(); });
  document.getElementById("btn-csv").addEventListener("click", csv);
  document.getElementById("btn-fund").addEventListener("click", copiarFund);
  const atalhosChoque = () => document.querySelectorAll("#atalhos-choque button").forEach(b => b.setAttribute("aria-pressed", String(+b.dataset.v === CHOQUE && CHOQUE_UN === "rs")));
  document.getElementById("choque").addEventListener("input", e => { const v = parseNum(e.target.value); if (v == null) return; CHOQUE = v; atalhosChoque(); sensibilidade(resolver().se); });
  document.getElementById("atalhos-choque").addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return;
    CHOQUE = +b.dataset.v; CHOQUE_UN = "rs"; document.getElementById("choque").value = n(CHOQUE); document.querySelector('input[name="choque-un"][value="rs"]').checked = true;
    atalhosChoque(); sensibilidade(resolver().se); });
  document.querySelectorAll('input[name="choque-un"]').forEach(i => i.addEventListener("change", () => { CHOQUE_UN = i.value; atalhosChoque(); sensibilidade(resolver().se); }));
  abas("abas-fund", v => { PFUND = v; tabelaFund(); });
  document.getElementById("btn-todos").addEventListener("click", () => {
    const v = parseNum(document.getElementById("valor-todos").value); if (v == null) return;
    ENT = {}; ANOS.forEach(y => { ENT[`A${y}`] = v; }); salvar(); atualizar();
  });
  document.getElementById("btn-limpar").addEventListener("click", () => { ENT = {}; salvar(); atualizar(); });
  document.querySelectorAll('input[name="saz"]').forEach(i => { i.checked = i.value === SAZMODO; i.addEventListener("change", () => { SAZMODO = i.value; salvar(); atualizar(); }); });

  document.getElementById("rot-horiz").textContent = `Horizonte: ${rotLongo(meta.horizonte[0])} a ${rotLongo(meta.horizonte[1])}`;
  document.getElementById("meta").innerHTML = `<span>Premissas:</span><span>Deck NEWAVE ${rot(meta.deck)}</span><span>Modelo ${meta.versao}</span>` +
    `<span>Dados horários até ${dataBr(meta.dados_ate)}</span><span>${M[0].cen.length} cenários climáticos</span><span class="atualizado">Rodada de ${dataHoraBr(meta.rodada)}</span>`;
  desenharCurva(); fundamentos(); tabelaFund(); historicoReal(); atualizar();
})();
