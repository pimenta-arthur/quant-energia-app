// Página "Compra e venda NE e N" (portada de pricing-descolamento-analytics, web/descolamento/compra_venda.html;
// leva promocao-quant-v5, D041 a D055). Dados: serving/pricing_descolamento/<chave>.json
// (qe_pricing_descolamento.publicacao e .compra_venda). A conta que depende da curva do SE digitada está em
// descolamento_conta.js; a da cotação (quantil, cauda, venda ancorada, swap) em compra_venda_conta.js (paridade com o Python).
"use strict";
(async function () {
  const CHAVES = ["meta", "sazonal_se", "meses", "historico_periodos", "fund_periodos", "cv_backtest", "cv_historico"];
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
  const CVB = D.cv_backtest, CVH = D.cv_historico, CVC = window.CVC;

  // ---------------------------------------------------------------- dados e utilidades
  const M = D.meses, SAZ = D.sazonal_se.fator, meta = D.meta;
  const CONTA = window.ContaDescolamento.criar(M, SAZ);
  const IDX = CONTA.IDX, ANOS = CONTA.ANOS, horas = CONTA.horas;
  const ano = p => +p.slice(0, 4), mesN = p => +p.slice(5, 7);
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
  try { const s = JSON.parse(localStorage.getItem("compra_venda.curva.v1") || "null"); if (s) { ENT = s.ent || {}; SAZMODO = s.saz || "plana"; } } catch (e) {}
  const salvar = () => { try { localStorage.setItem("compra_venda.curva.v1", JSON.stringify({ ent: ENT, saz: SAZMODO })); } catch (e) {} };
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

  // a pesquisa usa agregar(res, ms) e calcular(se): mesmas contas, agora do descolamento_conta.js
  const agregar = (res, ms) => CONTA.agregar(res, ms), calcular = (se, aj) => CONTA.calcular(se, aj);
  // fundamentos por mês (modelo e realizado, com sobra e folga) prontos do Python
  const FUNDM = Object.fromEntries(D.fund_periodos.serie.map(x => [x.mes, x]));
  function copiar(txt, id) {
    const ok = m => { const e = document.getElementById(id); e.textContent = m; setTimeout(() => { e.textContent = ""; }, 4000); };
    const plano = () => { const t = document.createElement("textarea"); t.value = txt; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); ok("Tabela copiada"); } catch (e) { ok("Selecione e copie manualmente"); } t.remove(); };
    try { navigator.clipboard.writeText(txt).then(() => ok("Tabela copiada; cole no Excel"), plano); } catch (e) { plano(); }
  }

  // ---------------------------------------------------------------- compra e venda
// ---------------------------------------------------------------- apetite (um botão) e parâmetros avançados
const CONSERVADOR = { compra: { p: 0.30, alfa: 0.10, lam: 1 }, venda: { p: 0.30, alfa: 0.10, lam: 1 }, ancora: true };
const copia = o => JSON.parse(JSON.stringify(o));
let EST = copia(CONSERVADOR);
try { const s = JSON.parse(localStorage.getItem("compra_venda.apetite.v3") || "null"); if (s && s.compra && s.venda && typeof s.ancora === "boolean") EST = s; } catch (e) {}
const salvarEst = () => { try { localStorage.setItem("compra_venda.apetite.v3", JSON.stringify(EST)); } catch (e) {} };
const mesmosParametros = () => JSON.stringify([EST.compra, EST.venda]) === JSON.stringify([CONSERVADOR.compra, CONSERVADOR.venda]);
const nomePolitica = () => !mesmosParametros() ? "Personalizado" : EST.ancora ? "Conservador" : "Conservador, sem âncora";
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const LADOS = [["compra", "c"], ["venda", "v"]];
function pintarApetite() {
  const nome = nomePolitica();
  document.getElementById("ap-desc").textContent = !mesmosParametros()
    ? "Parâmetros alterados em “Avançado”: só o λ = 1 com a âncora foi testado como política."
    : EST.ancora
      ? "Conservador: compra no pior ano climático do modelo (λ = 1). Venda no maior valor entre o melhor ano do modelo e o maior descolamento já realizado naquele mês (em proporção da folga do SE informado), mês a mês."
      : "Conservador, sem âncora: compra no pior ano climático e venda no melhor ano do modelo (λ = 1). No backtest, a venda do NE perdeu em 27% dos períodos.";
  document.getElementById("btn-restaurar").hidden = mesmosParametros() && EST.ancora;
  const m = document.getElementById("meta-ap"); if (m) m.textContent = nome;
  LADOS.forEach(([lado, s]) => {
    document.getElementById("p" + s).value = n(EST[lado].p * 100, 0);
    document.getElementById("a" + s).value = n(EST[lado].alfa * 100, 0);
    document.getElementById("l" + s).value = n(EST[lado].lam, 2);
  });
  document.getElementById("anc").checked = EST.ancora;
}
document.getElementById("btn-restaurar").addEventListener("click", () => { EST = copia(CONSERVADOR); salvarEst(); pintarApetite(); atualizar(); });
LADOS.forEach(([lado, s]) => {
  [["p", "p", 0.01, 0.50, 100], ["a", "alfa", 0.01, 0.50, 100], ["l", "lam", 0, 1, 1]].forEach(([pre, chave, lo, hi, esc]) => {
    document.getElementById(pre + s).addEventListener("change", e => {
      const v = parseNum(e.target.value); if (v == null) { pintarApetite(); return; }
      EST[lado][chave] = clamp(v / esc, lo, hi); salvarEst(); pintarApetite(); atualizar();
    });
  });
});
document.getElementById("anc").addEventListener("change", e => { EST.ancora = e.target.checked; salvarEst(); pintarApetite(); atualizar(); });

// ---------------------------------------------------------------- cotação por produto
let SUB = "NE", MODO = "d", PROD = "ano", RES = {};
// valor de cada ano climático no produto (média dos meses ponderada por horas); só anos presentes em todos os meses
function valoresPorAno(ms) {
  const H = horas(ms), wm = p => M[IDX[p]].horas / H;
  const ids = RES[ms[0]].cen.map(c => c.id).filter(id => ms.every(p => RES[p].cen.some(c => c.id === id)));
  return ids.map(id => ({ ano: id.split("|")[0], v: ms.reduce((a, p) => a + RES[p].cen.find(x => x.id === id)[SUB] * wm(p), 0) }));
}
// histórico realizado do mês do calendário: o maior (menos negativo) valor, em fração da folga, e o ano que o deu
function histMes(p) {
  const arr = (CVH[SUB] || {})[mesN(p)]; if (!arr || !arr.length) return null;
  const b = arr.reduce((a, x) => (x[1] > a[1] ? x : a)); return { f: b[1], ano: b[0], se: b[2], d: b[3] };
}
// SE e descolamento realizados do MESMO produto (mesmos meses do calendário) em um ano, ponderados por horas; só se todos os meses estão no histórico (até D−2)
function realizadoProduto(ms, ano) {
  let h = 0, se = 0, d = 0;
  for (const p of ms) {
    const mm = p.slice(5, 7), r = CVH.real[`${ano}-${mm}`]; if (!r) return null;
    const hh = new Date(ano, +mm, 0).getDate() * 24;
    h += hh; se += r[0] * hh; d += r[SUB === "NE" ? 1 : 2] * hh;
  }
  return { se: se / h, d: d / h };
}
function mesesDoProduto(ms) {
  return ms.map(p => { const h = histMes(p), folga = Math.max(RES[p].se - M[IDX[p]].piso, 0);
    return { mes: p, h: M[IDX[p]].horas, se: RES[p].se, anos: RES[p].cen.map(c => c[SUB]), ids: RES[p].cen.map(c => c.id.split("|")[0]), hist: h ? h.f * folga : null, info: h }; });
}
function cotarProduto(ms) {
  const g = ms.length ? agregar(RES, ms) : null; if (!g) return null;
  const anos = valoresPorAno(ms), amostra = anos.map(a => a.v), justo = g[SUB];
  if (!amostra.length) return null;
  const meses = mesesDoProduto(ms);
  let compra = CVC.cotarLado(amostra, "compra", EST.compra), limitada = false;
  let venda = EST.ancora ? CVC.vendaProduto(meses, EST.venda, true) : CVC.cotarLado(amostra, "venda", EST.venda);
  if (compra > justo) { compra = justo; limitada = true; }      // a compra nunca fica acima do justo (o justo oficial pode diferir da média dos anos completos)
  if (venda < justo) { venda = justo; limitada = true; }
  return { se: g.se, justo, compra, venda, anos, meses, ms, n: amostra.length, limitada };
}
function detalheCotacao(c) {
  const am = c.anos.map(a => a.v), pld = MODO === "pld", f = (v, se = c.se) => pld ? n(v + se, 1) : dn(v);
  const q = lado => CVC.viaQuantil(am, EST[lado].p)[lado], ca = lado => CVC.viaCauda(am, EST[lado].alfa, EST[lado].lam)[lado];
  const mn = Math.min(...am), mx = Math.max(...am);
  const anos = [...c.anos].sort((a, b) => a.ano.localeCompare(b.ano)).map(a => { const r = realizadoProduto(c.ms, +a.ano);
    return `<tr><td>${a.ano}</td><td class="n">${f(a.v)}</td><td>${a.v === mn && am.length > 1 ? "← mais descolado" : a.v === mx && am.length > 1 ? "← menos descolado" : ""}</td>` +
      `<td class="n ref">${r ? n(r.se, 0) : "—"}</td><td class="n ref">${r ? (pld ? n(r.se + r.d, 1) : dn(r.d)) : "—"}</td></tr>`; }).join("");
  const mesesTab = EST.ancora ? `<table class="det"><thead><tr><th>Mês</th><th class="n">SE</th><th class="n">Venda usada</th><th class="n">Venda do modelo</th><th class="n ref">Ano do modelo</th><th class="n">Venda pelo histórico</th>` +
    `<th class="n ref">Ano de referência</th><th class="n ref">SE realizado</th><th class="n ref">Descolamento realizado</th><th class="n ref">% da folga</th></tr></thead><tbody>` +
    c.meses.map(m => { const mod = CVC.precificar(m.anos, EST.venda).venda, usa = m.hist != null ? Math.max(mod, m.hist) : mod, i_ = m.info;
      const mx = Math.max(...m.anos), anoMod = Math.abs(mod - mx) < 0.05 ? m.ids[m.anos.indexOf(mx)] : "—";  // só é "o ano" quando a venda é o melhor cenário
      return `<tr><td>${rot(m.mes)}</td><td class="n">${n(m.se, 0)}</td><td class="n"><b>${f(usa, m.se)}</b></td><td class="n">${f(mod, m.se)}</td><td class="n ref">${anoMod}</td><td class="n">${m.hist != null ? f(m.hist, m.se) : "—"}</td>` +
        (i_ ? `<td class="n ref">${i_.ano}</td><td class="n ref">${n(i_.se, 0)}</td><td class="n ref">${dn(i_.d)}</td><td class="n ref">${n(i_.f * 100, 1)}%</td>` : `<td class="ref" colspan="4"></td>`) + `</tr>`; }).join("") +
    (() => { const H = c.meses.reduce((t, m) => t + m.h, 0), med = g => c.meses.reduce((t, m) => t + m.h * g(m), 0) / H,
        mod = m => CVC.precificar(m.anos, EST.venda).venda, usa = m => m.hist != null ? Math.max(mod(m), m.hist) : mod(m), seM = med(m => m.se);
      return `<tr style="border-top:1px solid var(--rule)"><td><b>média</b></td><td class="n">${n(seM, 0)}</td><td class="n"><b>${f(med(usa), seM)}</b></td><td class="n">${f(med(mod), seM)}</td><td class="n ref"></td>` +
        `<td class="n">${c.meses.every(m => m.hist != null) ? f(med(m => m.hist), seM) : "—"}</td><td class="ref" colspan="4"></td></tr>`; })() +
    `</tbody></table>` : "";
  return `<div style="display:flex;gap:28px;flex-wrap:wrap;padding:6px 0">` +
    `<table class="det"><thead><tr><th>Ano climático</th><th class="n">Valor</th><th></th><th class="n ref">SE realizado</th><th class="n ref">${pld ? "PLD realizado" : "Descolamento realizado"}</th></tr></thead><tbody>${anos}<tr><td><b>média (justo)</b></td><td class="n"><b>${f(am.reduce((a, b) => a + b, 0) / am.length)}</b></td><td></td><td></td><td></td></tr></tbody></table>` +
    `<table class="det"><thead><tr><th>Critério</th><th class="n">Compra</th><th class="n">Venda</th></tr></thead><tbody>` +
    `<tr><td>Quantil (p ${n(EST.compra.p * 100, 0)}% / ${n(EST.venda.p * 100, 0)}%)</td><td class="n">${f(q("compra"))}</td><td class="n">${f(q("venda"))}</td></tr>` +
    `<tr><td>Cauda (α ${n(EST.compra.alfa * 100, 0)}% / ${n(EST.venda.alfa * 100, 0)}% · λ ${n(EST.compra.lam, 2)} / ${n(EST.venda.lam, 2)})</td><td class="n">${f(ca("compra"))}</td><td class="n">${f(ca("venda"))}</td></tr>` +
    `<tr><td><b>Cotação${EST.ancora ? " (venda ancorada no realizado)" : " (o mais conservador)"}</b></td><td class="n"><b>${f(c.compra)}</b></td><td class="n"><b>${f(c.venda)}</b></td></tr></tbody></table>` +
    mesesTab + `</div>` +
    (EST.ancora ? `<div class="leg">Venda do mês = o maior entre o melhor ano do modelo no mês e o maior descolamento já realizado naquele mês do calendário (em fração da folga, de 2021 até ${rot(CVH.ate)}) × a folga do SE informado (SE − piso). A média dos meses é ponderada por horas. A compra segue o pior ano do produto. Isso supõe que o descolamento é proporcional à folga.</div>` : "") +
    `<div class="leg">Em cinza: o SE e o ${pld ? "PLD" : "descolamento"} que de fato ocorreram nesse mesmo produto em cada ano (até ${rot(CVH.ate)}); “—” quando o período ainda não terminou.</div>` + (c.limitada ? `<div class="leg">A cotação foi limitada ao preço justo oficial (média mês a mês), que difere da média dos anos completos neste produto.</div>` : "") +
    (c.n <= 6 ? `<div class="leg">Só ${c.n} anos climáticos neste produto: com α = 10%, a cauda é o pior ano e o quantil interpola entre dois anos.</div>` : "");
}
function cotSub(ms, sub) { return comFiltro(sub, "d", () => cotarProduto(ms)); }
// cotação de um produto da lista do Resumo: o produto sozinho, ou (com "Fechar o ano") a contribuição dele para o preço do ano
let MEMO_K = {}, A_DET = null;   // A_DET = {rot, sub, lado}: descritivo aberto no Resumo
function cotRef(p, sub) {
  if (PROD === "ano") return cotSub(p.meses, sub);
  const a = PER.find(x => x.meses.includes(p.meses[0])); if (!a) return cotSub(p.meses, sub);
  const ch = `${a.y}|${sub}`; if (!(ch in MEMO_K)) MEMO_K[ch] = comFiltro(sub, "d", () => calcComp(a));
  const nivel = PROD === "sem" ? 1 : PROD === "tri" ? 2 : 3;
  return comFiltro(sub, "d", () => linhaProduto(MEMO_K[ch], p.rot, p.meses, nivel, CREF));
}
function tabelaCotacao() {
  const GR = [["Descolamento NE", "NE", false], ["Descolamento N", "N", false], ["PLD implícito NE", "NE", true], ["PLD implícito N", "N", true]], nc = COMPACTA_JUSTO ? 3 : 2;
  document.getElementById("tt-cot").textContent = "Compra e venda por produto: descolamento e PLD implícito do NE e do N, R$/MWh";
  MEMO_K = {};
  const L = produtos(PROD);
  let h = `<colgroup><col style="width:104px"><col style="width:64px"></colgroup><thead><tr><th rowspan="2">Produto</th><th rowspan="2">SE médio</th>` + GR.map(g => `<th class="gp" colspan="${nc}">${g[0]}</th>`).join("") + `</tr><tr>` +
    GR.map(() => `<th class="gp">Compra</th>${COMPACTA_JUSTO ? `<th>Justo</th>` : ""}<th>Venda</th>`).join("") + `</tr></thead><tbody>`;
  if (!Object.keys(RES).length) h += `<tr><td colspan="${2 + 4 * nc}" class="vazio-msg">Informe a curva do Sudeste acima para ver o resumo por produto.</td></tr>`;
  L.forEach(p => {
    const cs = { NE: cotRef(p, "NE"), N: cotRef(p, "N") }, c0 = cs.NE || cs.N; if (!c0) return;
    h += `<tr class="${p.parcial ? "parcial" : ""}"><td style="white-space:nowrap"><b>${p.rot}</b></td><td><div class="cel vazio" style="min-width:0">${n(c0.se, 1)}</div></td>` + GR.map(([, sub, pld]) => {
      const c = cs[sub]; if (!c) return `<td class="gp"><div class="cel vazio">—</div></td>${COMPACTA_JUSTO ? `<td><div class="cel vazio">—</div></td>` : ""}<td><div class="cel vazio">—</div></td>`;
      const b = pld ? c.se : 0, f = v => pld ? n(v + b, 1) : dn(v);
      const lado = (v, ld) => pld ? `<div class="cel">${f(v)}</div>` : `<button type="button" class="cel clic clic-a${A_DET && A_DET.rot === p.rot + PROD && A_DET.sub === sub && A_DET.lado === ld ? " ativo" : ""}" data-r="${p.rot}${PROD}" data-sub="${sub}" data-lado="${ld}" aria-label="Detalhar ${ld} do ${sub} em ${p.rot}"><b>${f(v)}</b></button>`, cls = pld ? "" : "ano-res";
      return `<td class="${cls} gp">${lado(c.compra, "compra")}</td>${COMPACTA_JUSTO ? `<td><div class="cel vazio">${f(c.justo)}</div></td>` : ""}<td class="${cls}">${lado(c.venda, "venda")}</td>`; }).join("") + `</tr>`;
    if (A_DET && A_DET.rot === p.rot + PROD && cs[A_DET.sub]) { const c = cs[A_DET.sub], r = { rot: p.rot, ms: p.meses, se: c.se, contrib: c.contrib || null };
      h += `<tr class="meses-row"><td colspan="${2 + 4 * nc}" style="text-align:left">${comFiltro(A_DET.sub, "d", () => descritivoProduto(r, A_DET.lado))}</td></tr>`; }
  });
  document.getElementById("tab-cot").innerHTML = h + "</tbody>";
  document.querySelectorAll("#tab-cot .clic-a").forEach(b => b.addEventListener("click", () => { const d = { rot: b.dataset.r, sub: b.dataset.sub, lado: b.dataset.lado };
    A_DET = A_DET && A_DET.rot === d.rot && A_DET.sub === d.sub && A_DET.lado === d.lado ? null : d; tabelaCotacao(); }));
}
function csvCot() {
  MEMO_K = {};
  const c = v => (v == null || !isFinite(v) ? "" : v.toFixed(2).replace(".", ","));
  const cab = ["produto", "SE"]; ["desc_NE", "desc_N", "PLD_NE", "PLD_N"].forEach(g => ["compra", "justo", "venda"].forEach(k => cab.push(`${g}_${k}`)));
  const lin = produtos(PROD).map(p => { const cs = { NE: cotRef(p, "NE"), N: cotRef(p, "N") }, c0 = cs.NE || cs.N; if (!c0) return null;
    const bl = (sub, pld) => { const x = cs[sub]; return x ? ["compra", "justo", "venda"].map(k => c(x[k] + (pld ? x.se : 0))) : ["", "", ""]; };
    return [p.rot, c(c0.se), ...bl("NE", false), ...bl("N", false), ...bl("NE", true), ...bl("N", true)].join("\t"); }).filter(Boolean);
  const txt = [cab.join("\t"), ...lin].join("\n");
  const ok = m => { const e = document.getElementById("copiado"); e.textContent = m; setTimeout(() => { e.textContent = ""; }, 4000); };
  const plano = () => { const t = document.createElement("textarea"); t.value = txt; document.body.appendChild(t); t.select(); try { document.execCommand("copy"); ok("Tabela copiada"); } catch (e) { ok("Selecione e copie manualmente"); } t.remove(); };
  try { navigator.clipboard.writeText(txt).then(() => ok("Tabela copiada; cole no Excel"), plano); } catch (e) { plano(); }
}

// ---------------------------------------------------------------- como esse apetite teria se saído (backtest, cada período com o mesmo peso)
function painelBacktest() {
  const tipo = PROD === "sem" ? "sem" : "tri", nome = tipo === "sem" ? "semestres" : "trimestres";
  const casos = CVB.casos.filter(c => c.tipo === tipo);
  const porPer = {};
  casos.forEach(c => {
    const am = c.anos[SUB], r = c.real[SUB], meses = c.meses.map(m => ({ h: m.h, anos: m.anos[SUB], hist: m.hist[SUB] }));
    const comp = CVC.cotarLado(am, "compra", EST.compra);
    const ven = EST.ancora ? CVC.vendaProduto(meses, EST.venda, true) : CVC.cotarLado(am, "venda", EST.venda);
    (porPer[c.periodo] = porPer[c.periodo] || []).push({ pc: r < comp ? 1 : 0, pv: r > ven ? 1 : 0, gc: r - comp, gv: ven - r, l: ven - comp });
  });
  const per = Object.keys(porPer).sort(), med = (L, k) => L.reduce((a, x) => a + x[k], 0) / L.length;
  const linhas = per.map(p => ({ p, n: porPer[p].length, pc: med(porPer[p], "pc"), pv: med(porPer[p], "pv"), gc: med(porPer[p], "gc"), gv: med(porPer[p], "gv"), l: med(porPer[p], "l") }));
  const tot = k => linhas.reduce((a, x) => a + x[k], 0) / linhas.length;      // média entre períodos: cada um pesa igual
  const pct0 = v => n(v * 100, 0) + "%", alto = (v, lado) => v > EST[lado].p + 0.15 ? ` class="n alto"` : ` class="n"`;
  document.getElementById("tt-bt").textContent = `${SUB}, ${nome} fechados: ${casos.length} casos em ${per.length} períodos` + (PROD === "mes" || PROD === "ano" ? ` (para ${PROD === "mes" ? "mês" : "ano"} não há casos fechados suficientes; mostrando trimestres)` : "");
  let h = `<thead><tr><th>Período</th><th class="n">Casos</th><th class="n">Perda da compra</th><th class="n">Perda da venda</th><th class="n">Ganho médio compra</th><th class="n">Ganho médio venda</th><th class="n">Largura</th></tr></thead><tbody>`;
  linhas.forEach(x => { h += `<tr><td>${x.p}</td><td class="n">${x.n}</td><td${alto(x.pc, "compra")}>${pct0(x.pc)}</td><td${alto(x.pv, "venda")}>${pct0(x.pv)}</td><td class="n">${sn(x.gc, 1)}</td><td class="n">${sn(x.gv, 1)}</td><td class="n">${n(x.l, 1)}</td></tr>`; });
  h += `<tr class="modelo"><td><b>Média dos períodos</b></td><td class="n">${casos.length}</td><td${alto(tot("pc"), "compra")}><b>${pct0(tot("pc"))}</b></td><td${alto(tot("pv"), "venda")}><b>${pct0(tot("pv"))}</b></td><td class="n"><b>${sn(tot("gc"), 1)}</b></td><td class="n"><b>${sn(tot("gv"), 1)}</b></td><td class="n"><b>${n(tot("l"), 1)}</b></td></tr>`;
  document.getElementById("tab-bt").innerHTML = h + "</tbody>";
  document.getElementById("leg-bt").innerHTML = `Política <b>${nomePolitica()}</b> (compra λ ${n(EST.compra.lam, 2)}, venda λ ${n(EST.venda.lam, 2)}${EST.ancora ? ", venda ancorada no realizado" : ""}), nos ${nome} que o modelo já tinha treino: a <b>compra</b> perdeu em ${pct0(tot("pc"))} dos períodos e a <b>venda</b> em ${pct0(tot("pv"))}. ` +
    `Perda = o descolamento realizado ficou abaixo do preço de compra (ou acima do de venda). Em vermelho, mais de 15 pontos acima do p escolhido. O erro é comum a todos os decks do mesmo período: o resultado é &ldquo;tudo ou nada&rdquo; por período. ` +
    `Backtest da v2.2 (decks de ${rot(CVB.meta.decks[0])} a ${rot(CVB.meta.decks.at(-1))}, alvos de ${rot(CVB.meta.alvos[0])} a ${rot(CVB.meta.alvos[1])}), SE realizado como insumo; o histórico usa só dados até D−2; ganhos em R$/MWh por unidade de energia do período. ` +
    (EST.ancora ? `A regra da venda ancorada foi escolhida depois de ver dados e testada nesta mesma amostra: não é garantia.` : "");
}

// ---------------------------------------------------------------- orquestração
// cálculo da composição de um ano (usado pela tabela "Composição do ano" e pela grade de produtos)
function calcComp(a) {
  const c = a && Object.keys(RES).length ? cotarProduto(a.meses) : null; if (!c) return null;
  const H = horas(a.meses), ancora = EST.ancora, vA = valoresPorAno(a.meses); if (!vA.length) return null;
  const pior = vA.reduce((x, y) => (y.v < x.v ? y : x)), melhor = vA.reduce((x, y) => (y.v > x.v ? y : x));
  const usa = m => { const mod = CVC.precificar(m.anos, EST.venda).venda; return m.hist != null ? Math.max(mod, m.hist) : mod; };
  const porMes = {}; c.meses.forEach(m => { porMes[m.mes] = usa(m); });
  const doAno = (ms, ref) => valoresPorAno(ms).find(x => x.ano === ref.ano).v;
  const venda0 = ms => ancora ? ms.reduce((t, p) => t + porMes[p] * M[IDX[p]].horas, 0) / horas(ms) : doAno(ms, melhor);
  const compra0 = ms => doAno(ms, pior);
  const dC = c.compra - compra0(a.meses), dV = c.venda - venda0(a.meses);
  const lin = (rot, ms, nivel) => { const g = agregar(RES, ms), co = compra0(ms) + dC, ve = venda0(ms) + dV;
    return { rot, ms, nivel, w: horas(ms) / H, se: g.se, compra: co, justo: g[SUB], venda: ve }; };
  return { c, H, ancora, pior, melhor, dC, dV, lin };
}
// linha de um produto: contribuição no ano quando o ano está precificado; senão (curva informada só em semestre, trimestre ou mês)
// a cotação do produto sozinho, ou null se faltar preço em algum mês
function comFiltro(sub, modo, fn) { const s0 = SUB, m0 = MODO; SUB = sub; MODO = modo; try { return fn(); } finally { SUB = s0; MODO = m0; } }
function linhaProduto(k, rot, ms, nivel, modo) {
  if (!ms.length) return null;
  const c = cotarProduto(ms), contrib = k ? k.lin(rot, ms, nivel) : null;
  const solo = c ? { rot, ms, nivel, w: contrib ? contrib.w : 0, se: c.se, compra: c.compra, justo: c.justo, venda: c.venda } : null;
  const base = modo === "ano" && contrib ? contrib : solo;
  return base ? { ...base, solo, contrib } : null;
}
// indicativo (D074): a compra do ano montada pelos trimestres cotados sozinhos (média por horas). Só para ano completo; não é a
// cotação do ano (o backtest não mostrou ganho de risco em cotar o ano assim), é a conta de quem fecha trimestre a trimestre.
function compraAnoPelosTri(ms) {
  const a = PER.find(x => x.meses.length === 12 && x.meses.length === ms.length && x.meses.every(p => ms.includes(p))); if (!a) return null;
  const cs = a.T.map(t => cotarProduto(t.meses)); if (cs.some(x => !x)) return null;
  return a.T.reduce((t, x, i) => t + cs[i].compra * horas(x.meses), 0) / horas(a.meses);
}
function descritivoProduto(r, ld) {
  const pld = MODO === "pld", f = (v, se) => pld ? n(v + se, 1) : dn(v), c = cotarProduto(r.ms); if (!c) return "";
  const sozinho = c[ld], contrib = r.contrib ? r.contrib[ld] : null, dif = contrib != null && Math.abs(sozinho - contrib) > 0.05;
  const pt = ld === "compra" ? compraAnoPelosTri(r.ms) : null;
  return `<div class="leg" style="margin:4px 0"><b>${ld === "compra" ? "Compra" : "Venda"} de ${r.rot}</b> · sozinho <b>${f(sozinho, c.se)}</b>` +
    (dif ? ` · fechando o ano <b>${f(contrib, r.contrib.se)}</b>` : "") + (pt == null ? "" : ` · pelos trimestres <b>${f(pt, c.se)}</b>`) + `</div>${detalheCotacao(c)}`;
}
let CSUB = "NE", CMODO = "d", CREF = "sozinho", COMPACTA_JUSTO = false, COMPACTA_DET = null; const COMPACTA_ABERTOS = new Set();
function gradeCompacta() { comFiltro(CSUB, CMODO, gradeCompacta_); }
function gradeCompacta_() {
  // conferência do ano (uma linha da tabela "Conferir o ano"): compra do ano sozinho × média por horas dos semestres e dos trimestres
  // sozinhos; venda (igual nas três contas)
  const conferir = (a, k, cols) => {
    if (!k || !cols[0]) return null;
    const pld = MODO === "pld", f = (v, se) => pld ? n(v + se, 1) : dn(v), y = cols[0], solo = y.solo || y;
    if (cols.slice(1, 3).filter(Boolean).length < 2) return null;
    const media = (rs, l) => { const W = rs.reduce((t, r) => t + r.w, 0); return rs.reduce((t, r) => t + r.w * r[l], 0) / W; };
    const S = cols.slice(1, 3).map(r => ({ ...(r.solo || r), w: r.w })), T = cols.slice(3).filter(Boolean).map(r => ({ ...(r.solo || r), w: r.w }));
    const pt = compraAnoPelosTri(a.meses), vS = media(S, "venda"), vT = T.length === 4 ? media(T, "venda") : null;
    const vendas = [solo.venda, vS, vT].filter(v => v != null), vIgual = vendas.every(v => Math.abs(v - solo.venda) < 0.06);
    return `<tr><td><b>${a.rot}</b></td><td class="n"><b>${f(solo.compra, y.se)}</b></td><td class="n">${f(media(S, "compra"), y.se)}</td><td class="n">${pt == null ? "—" : f(pt, y.se)}</td>` +
      `<td class="n">${vIgual ? f(solo.venda, y.se) : `${f(solo.venda, y.se)} · ${f(vS, y.se)} · ${vT == null ? "—" : f(vT, y.se)}`}</td></tr>`;
  };

  const tab = document.getElementById("tab-compacta"), pld = MODO === "pld", f = (v, se) => pld ? n(v + se, 1) : dn(v);
  document.getElementById("tt-compacta").textContent = `Compra / venda e justo ${pld ? "(PLD implícito)" : "do descolamento"} do ${SUB} por ano, semestre e trimestre, R$/MWh`;
  if (!Object.keys(RES).length) { tab.innerHTML = `<tbody><tr><td class="vazio-msg">Informe a curva do Sudeste acima para ver a tabela.</td></tr></tbody>`; return; }
  const par = (r, ano, y, j) => { const at = l => COMPACTA_DET && COMPACTA_DET.y === y && COMPACTA_DET.col === j && COMPACTA_DET.lado === l;
    const b = (l, rot) => `<button type="button" class="cel clic cmp${at(l) ? " ativo" : ""}" data-y="${y}" data-col="${j}" data-lado="${l}" aria-label="Detalhar ${l} de ${rot}">${ano ? `<b>${f(r[l], r.se)}</b>` : f(r[l], r.se)}</button>`;
    return `<div class="cmp-par">${b("compra", r.rot)}<span class="barra">/</span>${b("venda", r.rot)}</div><span class="fx">SE ${n(r.se, 1)}${COMPACTA_JUSTO ? ` · ${f(r.justo, r.se)}` : ""}</span>`; };
  let h = `<thead><tr><th>Ano</th><th>Ano</th><th>1º sem</th><th>2º sem</th><th>T1</th><th>T2</th><th>T3</th><th>T4</th><th>Meses</th></tr></thead><tbody>`;
  const confs = [];
  PER.forEach(a => {
    const k = calcComp(a);
    const cols = [linhaProduto(k, a.rot, a.meses, 0, CREF), ...a.S.map(x => linhaProduto(k, x.rot, x.meses, 1, CREF)), ...a.T.map(x => linhaProduto(k, x.rot, x.meses, 2, CREF))], aberto = COMPACTA_ABERTOS.has(a.y);
    confs.push(conferir(a, k, cols));
    if (cols.every(c => !c)) return;
    h += `<tr><td><b>${a.rot}</b></td>` + cols.map((r, j) => `<td class="${j === 0 ? "ano-res" : ""}">${r ? par(r, j === 0, a.y, j) : `<div class="cel vazio">—</div>`}</td>`).join("") +
      `<td><button type="button" class="exp" data-a="${a.y}" aria-expanded="${aberto}">${aberto ? "▾ ocultar" : "▸ abrir"}</button></td></tr>`;
    if (aberto) { const ms = a.meses.map(pp => linhaProduto(k, rot(pp), [pp], 3, CREF)).filter(Boolean);
      const lados = ["se", "compra", "venda", ...(COMPACTA_JUSTO ? ["justo"] : [])], NM = { se: "SE", compra: "compra", venda: "venda", justo: "justo" };
      h += `<tr class="meses-row"><td colspan="9"><table class="det" style="margin:0 auto"><thead><tr><th></th>${ms.map(r => `<th class="n">${r.rot}</th>`).join("")}</tr></thead><tbody>` +
        lados.map(lado => `<tr><td class="leg">${NM[lado]}</td>${ms.map(r => {
          if (lado === "se") return `<td class="n">${n(r.se, 0)}</td>`;
          if (lado === "justo") return `<td class="n">${f(r[lado], r.se)}</td>`;
          const at = COMPACTA_DET && COMPACTA_DET.y === a.y && COMPACTA_DET.mes === r.ms[0] && COMPACTA_DET.lado === lado;
          return `<td class="n"><button type="button" class="cel clic cmp${at ? " ativo" : ""}" data-y="${a.y}" data-mes="${r.ms[0]}" data-lado="${lado}" aria-label="Detalhar ${lado} de ${r.rot}">${f(r[lado], r.se)}</button></td>`; }).join("")}</tr>`).join("") + `</tbody></table></td></tr>`;
      if (COMPACTA_DET && COMPACTA_DET.y === a.y && COMPACTA_DET.mes) { const r = ms.find(x => x.ms[0] === COMPACTA_DET.mes);
        if (r) h += `<tr class="meses-row"><td></td><td colspan="8" style="text-align:left">${descritivoProduto(r, COMPACTA_DET.lado)}</td></tr>`; } }
    if (COMPACTA_DET && COMPACTA_DET.y === a.y && COMPACTA_DET.col != null) { const r = cols[COMPACTA_DET.col];
      if (r) h += `<tr class="meses-row"><td></td><td colspan="8" style="text-align:left">${descritivoProduto(r, COMPACTA_DET.lado)}</td></tr>`; }
  });
  const lin = confs.filter(Boolean);
  document.getElementById("compacta-conf").innerHTML = lin.length ? `<table class="det"><thead><tr><th rowspan="2">Ano</th><th class="grupo" colspan="3">Compra</th><th class="n" rowspan="2">Venda</th></tr>` +
    `<tr><th class="n">Pelo ano</th><th class="n">Pelos semestres</th><th class="n">Pelos trimestres</th></tr></thead><tbody>${lin.join("")}</tbody></table>` : "";
  tab.innerHTML = h + "</tbody>";
  tab.querySelectorAll(".exp").forEach(b => b.addEventListener("click", () => { const y = +b.dataset.a; COMPACTA_ABERTOS.has(y) ? COMPACTA_ABERTOS.delete(y) : COMPACTA_ABERTOS.add(y); gradeCompacta(); }));
  tab.querySelectorAll(".clic").forEach(b => b.addEventListener("click", () => {
    const d = b.dataset.mes ? { y: +b.dataset.y, mes: b.dataset.mes, lado: b.dataset.lado } : { y: +b.dataset.y, col: +b.dataset.col, lado: b.dataset.lado };
    const igual = COMPACTA_DET && COMPACTA_DET.y === d.y && COMPACTA_DET.col === d.col && COMPACTA_DET.mes === d.mes && COMPACTA_DET.lado === d.lado;
    COMPACTA_DET = igual ? null : d; gradeCompacta(); }));
}
// ---------------------------------------------------------------- swap
// spread = PLD(perna que recebe) − k · PLD(perna que paga), k = (volume · horas pagos) ÷ (volume · horas recebidos).
// Com o SE em uma perna: o risco climático vem só do descolamento da outra (o SE é a curva da mesa) e a conta é a cotação do produto deslocada.
// NE × N (ou o mesmo submercado em períodos diferentes): spread ano climático a ano climático (D045), sem a âncora no realizado.
const SW = { rec: { sub: "NE", tipo: "ano", i: -1 }, pag: { sub: "SE", tipo: "ano", i: -1 } };
function comRES(r, fn) { const r0 = RES; RES = r; try { return fn(); } finally { RES = r0; } }
function swapPeriodos(tipo) { return produtos(tipo); }
function swapPreencher(lado) {
  const L = SW[lado], ps = swapPeriodos(L.tipo), sel = document.getElementById(`sw-${lado}-per`);
  if (L.i < 0 || L.i >= ps.length) { L.i = Math.max(0, ps.findIndex(x => !x.parcial)); }
  sel.innerHTML = ps.map((x, i) => `<option value="${i}"${i === L.i ? " selected" : ""}>${x.rot}${x.parcial ? " (parcial)" : ""}</option>`).join("");
}
function swapPerna(lado) {
  const L = SW[lado], ps = swapPeriodos(L.tipo), p = ps[L.i]; if (!p) return null;
  const ov = parseNum(document.getElementById(`sw-${lado}-se`).value), vol = parseNum(document.getElementById(`sw-${lado}-vol`).value);
  const g = p.meses.every(q => RES[q]) ? agregar(RES, p.meses) : null;
  return { lado, sub: L.sub, p, ms: p.meses, h: horas(p.meses), ov, se: ov != null ? ov : (g ? g.se : null), vol };
}
function swapCalcular() {
  const R = swapPerna("rec"), P = swapPerna("pag"); if (!R || !P) return { erro: "Período indisponível." };
  for (const x of [R, P]) if (x.se == null) return { erro: `Informe o SE da perna que ${x === R ? "recebe" : "paga"}: na curva acima, para todos os meses do período, ou no campo da perna.` };
  if (!(R.vol > 0) || !(P.vol > 0)) return { erro: "Informe os volumes (MWm) das duas pernas." };
  const k = (P.vol * P.h) / (R.vol * R.h), nr = R.sub !== "SE", np = P.sub !== "SE";
  const resLeg = x => x.ov != null ? calcular(Object.fromEntries(x.ms.map(q => [q, x.ov]))) : RES;
  let q, notas = [], d = null;
  if (nr !== np) {
    const S = nr ? R : P, SE = nr ? P : R, c = comRES(resLeg(S), () => cotSub(S.ms, S.sub));
    if (!c) return { erro: `Faltam meses com SE para o período da perna ${S.sub}.` };
    d = { compra: c.compra, justo: c.justo, venda: c.venda, sub: S.sub, rot: S.p.rot };
    q = CVC.swapComSE(nr, S.se, d, SE.se, k);
  } else if (nr && np) {
    const vet = x => comRES(resLeg(x), () => comFiltro(x.sub, "d", () => valoresPorAno(x.ms)));
    const vr = vet(R), vp = vet(P), anos = vr.map(a => a.ano).filter(a => vp.some(b => b.ano === a));
    if (!anos.length) return { erro: "Sem ano climático em comum entre as duas pernas." };
    q = CVC.swapVetor(anos.map(a => R.se + vr.find(b => b.ano === a).v), anos.map(a => P.se + vp.find(b => b.ano === a).v), k, EST.compra, EST.venda);
    notas.push(`Spread calculado ano climático a ano climático (${anos.length} anos) e cotado com a mesma política de risco; sem a âncora no realizado, que ainda não foi definida para duas pernas com descolamento. Em períodos diferentes, usar o mesmo ano nas duas pernas pode subestimar o risco.`);
  } else { const sp = R.se - k * P.se; q = { compra: sp, justo: sp, venda: sp }; notas.push("As duas pernas são o SE: não há risco climático, só a diferença de curvas."); }
  if (Math.abs(k - 1) > 0.005) notas.push(`Volume × horas diferentes entre as pernas: k = ${n(k, 3)} (a perna que paga entra multiplicada por k; o SE líquido que sobra fica por conta da mesa).`);
  return { R, P, k, q, d, notas, base: R.vol * R.h };
}
function swapRender() {
  const aviso = document.getElementById("sw-aviso"), t = document.getElementById("sw-res"), leg = document.getElementById("sw-leg");
  const c = swapCalcular();
  if (c.erro) { aviso.innerHTML = `<span>⚠ ${c.erro}</span>`; t.innerHTML = ""; leg.textContent = ""; return; }
  aviso.innerHTML = c.notas.map(x => `<span>⚠ ${x}</span>`).join("");
  const linha = (nome, v, forte) => `<tr><td><b>${nome}</b></td><td class="n${forte ? " alvo" : ""}">${forte ? `<b>${dn(v)}</b>` : dn(v)}</td><td class="n">${n(v * c.base, 0)}</td></tr>`;
  t.innerHTML = `<thead><tr><th>Swap</th><th class="n">Spread (R$/MWh da perna que recebe)</th><th class="n">Valor no período (R$)</th></tr></thead><tbody>` +
    linha("Compra", c.q.compra, true) + linha("Justo", c.q.justo, false) + linha("Venda", c.q.venda, true) + `</tbody>`;
  const pl = x => `${x.sub} · ${x.p.rot} · SE ${n(x.se, 1)} · ${n(x.vol, 1)} MWm × ${n(x.h, 0)} h`;
  leg.innerHTML = `Recebe: ${pl(c.R)}. Paga: ${pl(c.P)}. Spread = PLD de quem recebe − k × PLD de quem paga (k = ${n(c.k, 3)}). ` +
    (c.d ? `Descolamento do ${c.d.sub} em ${c.d.rot}: compra ${dn(c.d.compra)}, justo ${dn(c.d.justo)}, venda ${dn(c.d.venda)}. ` : "") +
    `Comprar o swap a X: você recebe o PLD da perna que recebe, paga o da perna que paga e paga X (ganho = spread − X); vender é o inverso. O SE de cada perna é a curva da mesa: o risco do SE não está no preço.`;
}
["rec", "pag"].forEach(lado => {
  swapPreencher(lado);
  const get = id => document.getElementById(`sw-${lado}-${id}`);
  get("sub").addEventListener("change", e => { SW[lado].sub = e.target.value; swapRender(); });
  get("tipo").addEventListener("change", e => { SW[lado].tipo = e.target.value; SW[lado].i = -1; swapPreencher(lado); swapRender(); });
  get("per").addEventListener("change", e => { SW[lado].i = +e.target.value; swapRender(); });
  ["se", "vol"].forEach(id => get(id).addEventListener("input", swapRender));
});

  // ---------------------------------------------------------------- gráfico do descolamento por mês
let GFSUB = "NE", GFMODO = "d";
function graficoMes() { comFiltro(GFSUB, GFMODO, graficoMes_); }
function graficoMes_() {
  const svg = document.getElementById("g-mes"), w = 1040, h = 280, mg = { l: 48, r: 12, t: 14, b: 28 };
  svg.replaceChildren();
  const ms = M.map(m => m.mes).filter(p => RES[p]);
  const pld = MODO === "pld";
  document.getElementById("tt-gf").textContent = `${pld ? "PLD implícito" : "Descolamento"} do ${SUB} por mês, R$/MWh`;
  document.getElementById("leg-gf").innerHTML = pld
    ? `<span><i class="l" style="border-color:var(--accent)"></i>PLD ${SUB} justo</span><span><i style="background:var(--faixa-proj)"></i>Faixa entre cenários</span><span><i class="l" style="border-color:var(--ink-3)"></i>SE informado</span><span><i class="t" style="border-color:var(--ink-3)"></i>Piso</span>`
    : `<span><i class="l" style="border-color:var(--accent)"></i>Preço justo</span><span><i style="background:var(--faixa-proj)"></i>Faixa entre cenários (mín–máx)</span>`;
  document.getElementById("leg-gf2").textContent = pld ? "PLD implícito = SE informado + descolamento. Piso do ano do deck." : "Média ponderada dos cenários climáticos; faixa = cenário mais e menos descolado em cada mês.";
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
      const ext = [...r.cen].sort((a, b) => a[SUB] - b[SUB]), ano = c => c.id.split("|")[0];
      let h = `<b>${rot(p)}</b> · SE ${n(r.se, 1)}<br>${pld ? "PLD " : ""}${SUB} ${fmt(base + r[SUB])} · faixa ${fmt(base + r[SUB + "min"])} a ${fmt(base + r[SUB + "max"])}`;
      // 1º semestre: trava o tronco N/NE→SE (sobra N+NE); 2º semestre: trava o limite de exportação do NE
      h += +p.slice(5, 7) <= 6
        ? `<br>Por quê (NE): trava ${pct(r.trava)} das horas · k ${n(fm.k, 2)}<br>sobra NE ${dn(fm.sobra)} GW · hidráulica N ${n(fm.hidr_N, 1)} GW`
        : `<br>Por quê (NE): trava ${pct(r.trava)} das horas · k ${n(fm.k, 2)}<br>folga até o limite ${n(fm.folga, 1)} GW`;
      if (re && re.se != null && re["d_" + SUB] != null)
        h += `<br>Realizado ${rot(re.mes)}: SE ${n(re.se, 1)} · ${pld ? "PLD " + SUB + " " + n(re.se + re["d_" + SUB], 1) : SUB + " " + dn(re["d_" + SUB])}`;
      if (ext.length > 1) h += `<br>Extremos: mais descolado ${ano(ext[0])} · menos ${ano(ext.at(-1))}`;
      return h;
    });
  });
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
  const COLS_FUND = [["renov_NE", 1], ["carga_NE", 1], ["carga_N", 1], ["hidr_N", 1], ["hidr_NE", 1], ["sobra", 1], ["lim_NE", 1], ["folga", 1], ["trava", "%"], ["k", 2]];
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


  // ---------------------------------------------------------------- descolamento realizado (pronto do Python)
  const HP = D.historico_periodos;
  // ano de referência da venda ancorada: o ano do mês do calendário com a menor fração da folga já realizada (até D−2)
  function anoRefVenda(mes, sub) {
    const arr = (CVH[sub] || {})[String(+mes.slice(5, 7))]; if (!arr || !arr.length) return null;
    return arr.reduce((a, x) => (x[1] > a[1] ? x : a))[0];
  }
  let HSUB = "NE", HMODO = "d";
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
  function historicoRealizado() {
    const t1 = document.getElementById("hist-real"), t2 = document.getElementById("hist-meses"); if (!t1 || !HP.length) return;
    const pld = HMODO === "pld", SUB = HSUB, dsub = c => c["d_" + SUB];
    document.getElementById("tt-hist").textContent = `${pld ? "PLD implícito" : "Descolamento"} realizado do ${SUB}, R$/MWh`;
    // sombreado: uma cor, mais forte quanto mais descolado (escala = percentil 90 do descolamento mensal)
    const vm = HP.flatMap(a => Object.values(a.M)).map(c => Math.abs(dsub(c))).filter(v => v > 0).sort((a, b) => a - b), esc = vm.length ? vm[Math.floor(0.9 * (vm.length - 1))] : 1;
    const sombra = v => `background:color-mix(in srgb, var(--accent) ${Math.round(Math.min(1, Math.abs(v) / esc) * 42)}%, transparent)`;
    const CEL = [];
    const cel = (c, comSE, tdc = "") => {
      if (!c) return `<td class="${tdc}"><div class="cel vazio">—</div></td>`;
      const v = dsub(c), eref = c.meses.length === 1 && anoRefVenda(c.meses[0], SUB) === +c.meses[0].slice(0, 4);   // o ano que sustenta a venda ancorada deste mês do calendário
      CEL.push({ c, eref });
      return `<td class="${tdc}"><div class="cel${eref ? " ref-venda" : ""}" style="${sombra(v)}" data-i="${CEL.length - 1}"><b>${pld ? n(c.SE + v, 1) : dn(v)}</b>${comSE ? `<span class="fx">SE ${n(c.SE)}</span>` : ""}</div></td>`;
    };
    const gq = i => (i % 3 === 0 && i > 0 ? "gp" : "");   // separador vertical antes de abr, jul e out (início de cada trimestre)
    let h1 = `<thead><tr><th>Ano</th><th>Ano</th><th>1º sem</th><th>2º sem</th><th>T1</th><th>T2</th><th>T3</th><th>T4</th></tr></thead><tbody>`;
    let h2 = `<thead><tr><th>Ano</th>${MESES_ABR.map((m, i) => `<th class="${gq(i)}">${m}</th>`).join("")}</tr></thead><tbody>`;
    HP.forEach(a => {
      const rotA = String(a.ano) + (a.parcial ? "*" : "");
      h1 += `<tr><td><b>${rotA}</b></td>${cel(a.A, true)}${cel(a.S1, true)}${cel(a.S2, true)}${[1, 2, 3, 4].map(q => cel(a["T" + q], true)).join("")}</tr>`;
      h2 += `<tr><td><b>${rotA}</b></td>` + MESES_ABR.map((mm, i) => cel(a.M[`${a.ano}-${String(i + 1).padStart(2, "0")}`], true, gq(i))).join("") + "</tr>";
    });
    t1.innerHTML = h1 + "</tbody>"; t2.innerHTML = h2 + "</tbody>";
    document.querySelectorAll("#hist-real .cel[data-i], #hist-meses .cel[data-i]").forEach(el => dicaEm(el, () => {
      const { c, eref } = CEL[+el.dataset.i];
      return dicaHist(c) + (eref ? `<div style="margin-top:4px">◆ Ano de referência da venda ancorada neste mês do calendário (menor fração da folga já realizada).</div>` : "");
    }));
  }
  // ---------------------------------------------------------------- orquestração
  function atualizar() {
    const r = resolver(); pintarCurva(r);
    RES = calcular(r.se);
    tabelaCotacao(); gradeCompacta(); graficoMes(); swapRender(); painelBacktest();
  }
  function abas(id, cb) {
    document.getElementById(id).addEventListener("click", ev => { const b = ev.target.closest("button"); if (!b) return;
      document.querySelectorAll(`#${id} button`).forEach(x => x.setAttribute("aria-pressed", String(x === b))); cb(b.dataset.v); });
  }
  abas("abas-bt-sub", v => { SUB = v; painelBacktest(); });
  abas("abas-c-sub", v => { CSUB = v; COMPACTA_DET = null; gradeCompacta(); });
  abas("abas-c-modo", v => { CMODO = v; gradeCompacta(); });
  document.getElementById("c-ref").addEventListener("change", e => { CREF = e.target.checked ? "ano" : "sozinho"; tabelaCotacao(); gradeCompacta(); });
  document.getElementById("compacta-justo").addEventListener("change", e => { COMPACTA_JUSTO = e.target.checked; gradeCompacta(); tabelaCotacao(); });
  abas("abas-h-sub", v => { HSUB = v; historicoRealizado(); });
  abas("abas-h-modo", v => { HMODO = v; historicoRealizado(); });
  abas("abas-gf-sub", v => { GFSUB = v; graficoMes(); });
  abas("abas-gf-modo", v => { GFMODO = v; graficoMes(); });
  abas("abas-fund", v => { PFUND = v; tabelaFund(); });
  document.getElementById("btn-fund").addEventListener("click", copiarFund);
  abas("abas-prod", v => { PROD = v; tabelaCotacao(); painelBacktest(); });
  document.getElementById("btn-csv").addEventListener("click", csvCot);
  document.getElementById("btn-todos").addEventListener("click", () => {
    const v = parseNum(document.getElementById("valor-todos").value); if (v == null) return;
    ENT = {}; ANOS.forEach(y => { ENT[`A${y}`] = v; }); salvar(); atualizar();
  });
  document.getElementById("btn-limpar").addEventListener("click", () => { ENT = {}; salvar(); atualizar(); });
  document.querySelectorAll('input[name="saz"]').forEach(i => { i.checked = i.value === SAZMODO; i.addEventListener("change", () => { SAZMODO = i.value; salvar(); atualizar(); }); });

  document.getElementById("meta").innerHTML = `<span>Premissas:</span><span>Deck NEWAVE ${rot(meta.deck)}</span><span>Modelo ${meta.versao}</span>` +
    `<span>Dados horários até ${dataBr(meta.dados_ate)}</span><span>Política: <b id="meta-ap"></b></span><span class="atualizado">Rodada de ${dataHoraBr(meta.rodada)}</span>`;
  desenharCurva(); pintarApetite(); historicoRealizado(); fundamentos(); tabelaFund(); atualizar();
})();
