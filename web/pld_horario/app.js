// Página do PLD horário (acompanhamento). Desenho portado de risk-lab-dessem-analytics/web/pld_horario/app.js;
// as contas que não dependem do usuário vêm prontas do Python (serving/pld_horario/<chave>.json).
(async function () {
  const CHAVES = ["estado", "referencia", "dias_nivel", "dias_perfil", "semanas_perfil", "revisoes", "desvio_mensal", "dias_blocos", "horas", "contribuicao"];
  const D = {};
  try {
    await Promise.all(CHAVES.map(async k => {
      const r = await fetch(`/dados/pld_horario/${k}.json`, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${k}: ${r.status}`);
      D[k] = await r.json();
    }));
  } catch (e) {
    const el = document.getElementById("erro");
    el.hidden = false;
    el.textContent = `Dados da página indisponíveis (${e.message}). Rode: uv run qe pld_horario publicar`;
    return;
  }
  const ns = "http://www.w3.org/2000/svg";
  const MES = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"];
  const MESL = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];
  const SUBN = { SE: "SE/CO", S: "S", NE: "NE", N: "N" };
  const rot = p => `${MES[+p.slice(5, 7) - 1]}/${p.slice(2, 4)}`;
  const rotLongo = p => `${MESL[+p.slice(5, 7) - 1]} de ${p.slice(0, 4)}`;
  const dataBr = s => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(2, 4)}`;
  const n = (v, c = 0) => (v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }));
  const sn = (v, c = 0) => (v == null || !isFinite(v) ? "—" : (v > 0.0000001 ? "+" : v < -0.0000001 ? "−" : "") + n(Math.abs(v), c));
  const pct = v => (v == null ? "—" : n(v * 100) + "%");
  const DIR = { desconto: "Desconto", neutro: "Neutro", "prêmio": "Prêmio" };
  const CLS = { desconto: "desconto", neutro: "neutro", "prêmio": "premio" };
  // vale 8h–15h (8 horas; D054) e ponta 18h–21h, como em mensal.VALE / mensal.PONTA
  const VALE_H = [8, 9, 10, 11, 12, 13, 14, 15], PONTA_H = [18, 19, 20, 21], NV = VALE_H.length, NP = PONTA_H.length, NR = 24 - NV - NP;
  const BLOCOS = [["vale", "Vale 8h–15h", "var(--b-vale)"], ["ponta", "Ponta 18h–21h", "var(--b-ponta)"], ["demais", "Demais horas", "var(--b-demais)"]];
  const TIPOS = [["útil", "Dia útil", "var(--t-util)"], ["sábado", "Sábado", "var(--t-sab)"], ["domingo/feriado", "Domingo/feriado", "var(--t-dom)"]];
  const FAIXAS = [["Vale 8–15h", VALE_H], ["Ponta 18–21h", PONTA_H], ["Demais horas", [...Array(24).keys()].filter(hh => !VALE_H.includes(hh) && !PONTA_H.includes(hh))]];
  const classe = d => (d < -5 ? "desconto" : d > 5 ? "prêmio" : "neutro");
  const corAno = a => `var(--a${a}, var(--ink))`;
  const dica = document.getElementById("dica");
  function dicaEm(el, txt) {
    el.addEventListener("pointermove", e => { dica.innerHTML = typeof txt === "function" ? txt(e) : txt; dica.style.left = e.clientX + "px"; dica.style.top = e.clientY + "px"; dica.hidden = false; });
    el.addEventListener("pointerleave", () => { dica.hidden = true; });
  }
  function S(svg, tag, at, txt) { const e = document.createElementNS(ns, tag); for (const k in at) if (at[k] != null) e.setAttribute(k, at[k]); if (txt != null) e.textContent = txt; svg.appendChild(e); return e; }
  const passo = (lo, hi, alvo = 5) => { const r = (hi - lo) / alvo || 1, p = Math.pow(10, Math.floor(Math.log10(r))), f = r / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; };
  function eixo(lo, hi, alvo = 5, justo = false) {
    if (hi - lo < 1e-9) { hi = lo + 1; }
    const s = passo(lo, hi, alvo), f = justo ? s / 4 : s;  // justo: limite arredondado a 1/4 do passo (ex.: 616 → 650, não 800)
    const a = Math.floor(lo / f) * f, b = Math.ceil(hi / f) * f; const t = [];
    for (let v = Math.ceil(a / s) * s; v <= b + 1e-9; v += s) t.push(+v.toFixed(6));
    return { a, b, t };
  }
  function abas(id, itens, atual, aoMudar) {
    const box = document.getElementById(id); box.replaceChildren();
    itens.forEach(([v, rotulo]) => { const b = document.createElement("button"); b.type = "button"; b.textContent = rotulo; b.dataset.v = v; b.setAttribute("aria-pressed", String(String(v) === String(atual))); box.appendChild(b); });
    box.onclick = e => { const b = e.target.closest("button"); if (!b) return; box.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); aoMudar(b.dataset.v); };
  }
  const meses = [...new Set(D.dias_nivel.SE.map(r => r[0].slice(0, 7)))].sort();
  const ultMes = meses[meses.length - 1];
  const ref = D.referencia[0];
  // dias com deck do DESSEM ainda sem PLD publicado pela CCEE: PLD calculado do CMO do deck pela regra oficial (D048)
  const diaSeguinte = s => { const t = new Date(s + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() + 1); return t.toISOString().slice(0, 10); };
  const notaCalc = ref.ultimo_publicado && ref.ultimo_publicado < ref.ultimo_dia
    ? ` · PLD de ${dataBr(diaSeguinte(ref.ultimo_publicado)).slice(0, 5)} a ${dataBr(ref.ultimo_dia).slice(0, 5)} calculado do deck pela regra da CCEE (publicação oficial pendente)` : "";
  let SUB = "SE";

  // ---------- premissas no topo: datas da base e versão do modelo ----------
  const E = D.estado;
  document.getElementById("meta").innerHTML = [
    `<span>Dados até <b>${dataBr(E.ultimo_deck)}</b></span>`,
    `<span>PLD publicado pela CCEE até <b>${dataBr(E.ultimo_publicado)}</b></span>`,
    E.calculados ? `<span>${dataBr(E.calculados[0]).slice(0, 5)} a ${dataBr(E.calculados[1]).slice(0, 5)}: PLD calculado do deck</span>` : null,
    `<span>Modelo ${E.modelo} · vale ${E.vale[0]}h–${E.vale[1]}h · ponta ${E.ponta[0]}h–${E.ponta[1]}h</span>`,
    `<span class="atualizado">publicado em ${dataBr(E.gerado_em.slice(0, 10))} ${E.gerado_em.slice(11, 16)}</span>`,
  ].filter(Boolean).join("");

  // ---------- gráfico de linhas genérico ----------
  // series: [{nome, cor, pts: [[x, y]...], larg, tracejado, opac}]; xs: valores de x; rotX(x) rótulo
  function linhas(svg, o) {
    svg.replaceChildren();
    const w = o.w, h = o.h, m = { l: o.ml ?? 42, r: o.mr ?? 8, t: o.mt ?? 10, b: 24 };
    const ys = o.series.flatMap(s => s.pts.map(p => p[1])).filter(v => v != null && isFinite(v));
    if (!ys.length) { S(svg, "text", { x: w / 2, y: h / 2, "text-anchor": "middle" }, "sem dados no período"); return; }
    const ax = eixo(o.y0 != null ? Math.min(o.y0, ...ys) : Math.min(...ys), o.y1 != null ? Math.max(o.y1, ...ys) : Math.max(...ys), o.nt || 5, o.justo);
    const xs = o.xs, ix = new Map(xs.map((v, i) => [String(v), i]));
    const x = o.centro ? (v => m.l + (ix.get(String(v)) + 0.5) * (w - m.l - m.r) / xs.length)
      : (v => m.l + (xs.length === 1 ? 0.5 : ix.get(String(v)) / (xs.length - 1)) * (w - m.l - m.r));
    const y = v => m.t + (h - m.t - m.b) * (1 - (v - ax.a) / (ax.b - ax.a));
    (o.sombras || []).forEach(([a, b, cor]) => S(svg, "rect", { x: x(a) - 4, y: m.t, width: x(b) - x(a) + 8, height: h - m.t - m.b, fill: cor }));
    ax.t.forEach(t => { S(svg, "line", { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? "var(--ink-3)" : "var(--rule)" }); S(svg, "text", { x: m.l - 6, y: y(t) + 3, "text-anchor": "end" }, (o.fmtY || n)(t)); });
    xs.forEach((v, i) => { const r = o.rotX(v, i); if (r) S(svg, "text", { x: x(v), y: h - 6, "text-anchor": "middle", class: r.forte ? "forte" : null }, r.t ?? r); });
    if (o.antes) o.antes({ x, y, m, w, h, ix });
    (o.barras || []).forEach(b => { S(svg, "rect", { x: x(b.x) - b.lw / 2, y: y(Math.max(0, b.v)), width: b.lw, height: Math.abs(y(b.v) - y(0)), fill: b.cor, rx: 2 }); });
    o.series.forEach(s => {
      let d = "", pen = false;
      s.pts.forEach(([xv, yv]) => { if (yv == null || !isFinite(yv) || !ix.has(String(xv))) { pen = false; return; } d += `${pen ? "L" : "M"}${x(xv)},${y(yv)}`; pen = true; });
      if (d) S(svg, "path", { d, fill: "none", stroke: s.cor, "stroke-width": s.larg || 2, "stroke-dasharray": s.tracejado ? "4 3" : null, opacity: s.opac ?? 1, "stroke-linejoin": "round", "stroke-linecap": "round" });
      if (s.pontos) s.pts.forEach(([xv, yv]) => { if (yv != null && ix.has(String(xv))) S(svg, "circle", { cx: x(xv), cy: y(yv), r: 2.6, fill: s.cor }); });
    });
    if (o.rotFim) {
      const fins = o.series.filter(s => s.rotFim).map(s => { const p = [...s.pts].reverse().find(q => q[1] != null && ix.has(String(q[0]))); return p ? { s, y: y(p[1]), x: x(p[0]) } : null; }).filter(Boolean).sort((a, b) => a.y - b.y);
      for (let i = 1; i < fins.length; i++) if (fins[i].y - fins[i - 1].y < 11) fins[i].y = fins[i - 1].y + 11;
      fins.forEach(f => S(svg, "text", { x: f.x + 5, y: f.y + 3, style: `fill:${f.s.cor}`, class: "forte" }, f.s.rotFim));
    }
    const bw = o.centro ? (w - m.l - m.r) / xs.length : (w - m.l - m.r) / Math.max(1, xs.length - 1);
    const foco = S(svg, "line", { y1: m.t, y2: h - m.b, stroke: "var(--ink-3)", opacity: 0 });
    xs.forEach(v => {
      const a = S(svg, "rect", { x: x(v) - bw / 2, y: m.t, width: bw, height: h - m.t - m.b, fill: "transparent" });
      a.addEventListener("pointerenter", () => { foco.setAttribute("x1", x(v)); foco.setAttribute("x2", x(v)); foco.setAttribute("opacity", 0.6); });
      a.addEventListener("pointerleave", () => foco.setAttribute("opacity", 0));
      dicaEm(a, () => o.dica(v));
      if (o.clique) { a.style.cursor = "pointer"; a.addEventListener("click", () => o.clique(v)); }
    });
  }

  const HORAS = [...Array(24).keys()];
  const SOMBRAS = [[8, 15, "var(--sombra-vale)"], [18, 21, "var(--sombra-ponta)"]];
  const mesAnt = (() => { const a = +ultMes.slice(0, 4), m = +ultMes.slice(5, 7); return m === 1 ? `${a - 1}-12` : `${a}-${String(m - 1).padStart(2, "0")}`; })();
  // cores alternadas: itens vizinhos (dia a dia, revisão a revisão) nunca têm a mesma cor
  const PALETA = ["var(--accent)", "var(--v1)", "var(--t-dom)", "var(--am)", "var(--t-sab)", "var(--ink-2)"];
  const DSEM = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
  const diaSem = s => DSEM[new Date(s + "T12:00:00Z").getUTCDay()];
  const fimSemanaTipo = t => t === "sábado" || t === "domingo/feriado";

  // semana operativa (sábado a sexta) e revisão em curso
  const inicioSemana = d => { const t = new Date(d + "T12:00:00Z"); const k = (t.getUTCDay() + 1) % 7; t.setUTCDate(t.getUTCDate() - k); return t.toISOString().slice(0, 10); };
  const semAtual = inicioSemana(ref.ultimo_dia);
  const infoSemana = ini => { for (const sb of [SUB, "SE"]) for (const m of [ultMes, mesAnt]) { const s = (((D.semanas_perfil || {})[sb] || {})[m] || []).find(x => x.inicio === ini); if (s) return s; } return null; };
  const rvAtual = (infoSemana(semAtual) || {}).rv;

  function paginaAcompanhamento() {
    abas("abas-sub", Object.entries(SUBN), SUB, v => { SUB = v; desenharSub(); });

    // ---------- PLD médio do dia: DESSEM × DECOMP, com as revisões marcadas (D044, D045) ----------
    let PER_N = "mes";
    const REV = Object.fromEntries((D.revisoes || []).map(r => [r[0], r]));
    const somaDias = (ini, k) => { const t = new Date(ini + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() + k); return t.toISOString().slice(0, 10); };
    abas("abas-nivel", [["rev", `Revisão atual (RV${rvAtual ?? "?"})`], ["mes", `Mês corrente (${rot(ultMes)})`], ["3m", "Últimos 3 meses"], ["ano", `No ano (${ultMes.slice(0, 4)})`], ["todo", "Todo o histórico"]], PER_N, v => { PER_N = v; desenharNivel(); });
    function desenharNivel() {
      let rs = (D.dias_nivel || {})[SUB] || [];
      const ult = rs.length ? rs[rs.length - 1][0] : ref.ultimo_dia;
      if (PER_N === "rev") { const sa = inicioSemana(ult); rs = rs.filter(r => inicioSemana(r[0]) === sa); }
      else if (PER_N === "mes") rs = rs.filter(r => r[0].startsWith(ult.slice(0, 7)));
      else if (PER_N === "ano") rs = rs.filter(r => r[0].startsWith(ult.slice(0, 4)));
      else if (PER_N === "3m") { const d = new Date(ult + "T12:00:00Z"); d.setUTCMonth(d.getUTCMonth() - 3); const c = d.toISOString().slice(0, 10); rs = rs.filter(r => r[0] > c); }
      document.getElementById("tt-nivel").textContent = `PLD médio do dia: DESSEM e DECOMP vigente · ${SUBN[SUB]}`;
      const xs = rs.map(r => r[0]), u = rs[rs.length - 1] || [];
      // revisões do período: índices do primeiro e do último dia, médias de DECOMP e DESSEM nos dias mostrados
      const grupos = [];
      rs.forEach((r, i) => { const ini = inicioSemana(r[0]); let g = grupos[grupos.length - 1];
        if (!g || g.ini !== ini) { g = { ini, i0: i, i1: i, dias: [] }; grupos.push(g); }
        g.i1 = i; g.dias.push(r); });
      grupos.forEach(g => { const rv = REV[g.ini]; g.rv = rv ? rv[1] : null; g.pmo = rv ? rv[2] : null; g.fim = somaDias(g.ini, 6);
        g.decomp = g.dias.reduce((a, r) => a + r[2], 0) / g.dias.length; g.dessem = g.dias.reduce((a, r) => a + r[1], 0) / g.dias.length;
        g.emCurso = g.fim > ult; g.nome = g.rv == null ? "RV ?" : `RV${g.rv}`; });
      const porDia = new Map(); grupos.forEach(g => g.dias.forEach(r => porDia.set(r[0], g)));
      const modo = PER_N === "mes" || PER_N === "rev" ? "completo" : PER_N === "3m" ? "compacto" : "nenhum";
      const longo = xs.length > 400;
      const passoX = Math.max(1, Math.ceil(xs.length / 12));
      const rotXN = (d, i) => (longo ? (d.slice(5, 10) === "01-01" || i === 0 ? { t: d.slice(0, 4), forte: true } : null)
        : modo === "nenhum" ? (i % passoX === 0 ? dataBr(d).slice(0, 5) + "/" + d.slice(2, 4) : null)
        : modo === "compacto" ? (d.endsWith("-01") || i === 0 ? { t: rot(d.slice(0, 7)), forte: true } : null)
        : d.slice(8, 10));
      const descr = g => `${g.nome} · ${dataBr(g.ini).slice(0, 5)}–${dataBr(g.fim).slice(0, 5)}${g.emCurso ? ` · em curso (${g.dias.length} ${g.dias.length === 1 ? "dia" : "dias"})` : ""}`;
      document.getElementById("g-nivel").setAttribute("viewBox", `0 0 1040 ${modo === "nenhum" ? 270 : 320}`);
      linhas(document.getElementById("g-nivel"), { w: 1040, h: modo === "nenhum" ? 270 : 320, mt: modo === "nenhum" ? 10 : 58, mr: 80, xs, y0: 0,
        antes: ({ x, m, w, h }) => {
          if (modo === "nenhum") return;
          const svg = document.getElementById("g-nivel"), meio = xs.length > 1 ? (x(xs[1]) - x(xs[0])) / 2 : 20;
          divisoesDia(svg, xs.map(d => x(d) - meio), m, h);
          const niveis = [-1e9, -1e9];
          grupos.forEach((g, k) => {
            const xa = Math.max(m.l, x(xs[g.i0]) - meio), xb = Math.min(w - m.r, x(xs[g.i1]) + meio);
            if (k % 2 === 0) S(svg, "rect", { x: xa, y: m.t, width: xb - xa, height: h - m.t - m.b, fill: "var(--vazio)", opacity: 0.55 });
            S(svg, "line", { x1: xa, x2: xa, y1: 4, y2: h - m.b, stroke: "var(--ink-3)", opacity: 0.7 });
            S(svg, "line", { x1: xa, x2: xa, y1: h - m.b, y2: h - m.b + 12, stroke: "var(--ink-2)", "stroke-width": 1.6 });
            let l1, l2;
            if (modo === "completo") { l1 = descr(g); l2 = `DECOMP ${n(g.decomp, 0)} · DESSEM ${n(g.dessem, 0)}`; }
            else { const mudou = k === 0 || (grupos[k - 1].pmo !== g.pmo); l1 = g.nome + (mudou && g.pmo ? " " + MES[+g.pmo.slice(5, 7) - 1] : ""); l2 = `${n(g.decomp, 0)}·${n(g.dessem, 0)}`; }
            const larg = Math.max(l1.length, l2.length) * (modo === "completo" ? 6.3 : 5.9);
            let xt = xa + 3, anc = null; if (xt + larg > w - m.r) { xt = w - m.r; anc = "end"; }
            const ini = anc ? xt - larg : xt;
            const nv = ini > niveis[0] + 6 ? 0 : 1; niveis[nv] = anc ? xt : xt + larg;
            const y0 = 12 + nv * 24;
            S(svg, "text", { x: xt, y: y0, class: "forte", "text-anchor": anc }, l1);
            S(svg, "text", { x: xt, y: y0 + 11, "text-anchor": anc }, l2);
          });
        },
        series: [{ nome: "Piso", cor: "var(--ink-3)", larg: 1, tracejado: true, pts: rs.map(r => [r[0], r[3]]) },
          { nome: "DECOMP", cor: "var(--ink-3)", larg: longo ? 1.2 : 2, pts: rs.map(r => [r[0], r[2]]), rotFim: "DECOMP " + n(u[2]) },
          { nome: "DESSEM", cor: "var(--accent)", larg: longo ? 1.2 : 2, pts: rs.map(r => [r[0], r[1]]), rotFim: "DESSEM " + n(u[1]) }],
        rotFim: true,
        rotX: rotXN, centro: true,
        dica: d => { const r = rs.find(x => x[0] === d), g = porDia.get(d);
          return `<b>${dataBr(d)} ${diaSem(d)}</b>${r[5] ? " · " + r[5] : ""}<br>DESSEM ${n(r[1], 1)} · DECOMP ${n(r[2], 1)}<br>desvio ${sn(r[1] - r[2], 1)} · ${r[4]} h do vale no piso` +
            (g ? `<br><b>${descr(g)}</b><br>média da revisão no período: DECOMP ${n(g.decomp, 1)} · DESSEM ${n(g.dessem, 1)}` : ""); } });
      desenharNivelHora(rs, grupos, modo, rotXN, descr, porDia);
      document.getElementById("leg-nivel").textContent = modo === "completo" ? "Rótulo de cada revisão: datas de sábado a sexta, DECOMP (PLD semanal da revisão) e DESSEM médio dos dias mostrados. Faixas alternadas = uma revisão."
        : modo === "compacto" ? "Rótulo de cada revisão: RV (e o mês do PMO quando muda) e DECOMP · DESSEM médios dos dias mostrados. Datas e detalhes na dica. Faixas alternadas = uma revisão."
        : "Revisão de cada dia na dica.";
    }

    // divisão entre dias no eixo X (como no gráfico do topo): tique curto; com até ~45 dias, também linha pontilhada clara (D049)
    function divisoesDia(svg, xsDia, m, h) {
      const linha = xsDia.length <= 45;
      xsDia.forEach((xx, i) => {
        if (i === 0) return;
        if (linha) S(svg, "line", { x1: xx, x2: xx, y1: m.t, y2: h - m.b, stroke: "var(--ink-3)", "stroke-dasharray": "2 3", opacity: 0.35 });
        S(svg, "line", { x1: xx, x2: xx, y1: h - m.b, y2: h - m.b + (linha ? 8 : 5), stroke: "var(--ink-2)", "stroke-width": 1 });
      });
    }

    // gráfico horário alinhado embaixo do diário: cada dia ocupa a mesma largura, dividida em 24 horas (D046)
    function desenharNivelHora(rs, grupos, modo, rotX, descr, porDia) {
      const svg = document.getElementById("g-nivel-hora"); svg.replaceChildren();
      const w = 1040, h = 250, m = { l: 42, r: 80, t: 10, b: 24 }, N = rs.length;
      if (!N) { S(svg, "text", { x: w / 2, y: h / 2, "text-anchor": "middle" }, "sem dados no período"); return; }
      const curto = modo !== "nenhum";
      const dw = (w - m.l - m.r) / N, xd = i => m.l + i * dw, xc = i => xd(i) + dw / 2, xh = (i, hh) => xd(i) + (hh + 0.5) * dw / 24;
      const horas = new Map(); Object.values((D.dias_perfil || {})[SUB] || {}).flat().forEach(d => horas.set(d.data, d.pld));
      let vals = [];
      if (curto) rs.forEach(r => { const v = horas.get(r[0]); if (v) vals.push(...v); }); else rs.forEach(r => vals.push(r[6], r[7]));
      vals = vals.filter(v => v != null);
      const ax = eixo(0, Math.max(100, ...vals)), y = v => m.t + (h - m.t - m.b) * (1 - (v - ax.a) / (ax.b - ax.a));
      if (curto) grupos.forEach((g, k) => {
        const xa = xd(g.i0), xb = xd(g.i1 + 1);
        if (k % 2 === 0) S(svg, "rect", { x: xa, y: m.t, width: xb - xa, height: h - m.t - m.b, fill: "var(--vazio)", opacity: 0.55 });
        S(svg, "line", { x1: xa, x2: xa, y1: m.t, y2: h - m.b, stroke: "var(--ink-3)", opacity: 0.7 });
        S(svg, "line", { x1: xa, x2: xa, y1: h - m.b, y2: h - m.b + 12, stroke: "var(--ink-2)", "stroke-width": 1.6 });
      });
      ax.t.forEach(t => { S(svg, "line", { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? "var(--ink-3)" : "var(--rule)" }); S(svg, "text", { x: m.l - 6, y: y(t) + 3, "text-anchor": "end" }, n(t)); });
      if (curto) divisoesDia(svg, rs.map((_, i) => xd(i)), m, h);
      S(svg, "path", { d: rs.map((r, i) => `${i ? "L" : "M"}${xd(i)},${y(r[3])}L${xd(i + 1)},${y(r[3])}`).join(""), fill: "none", stroke: "var(--ink-3)", "stroke-dasharray": "4 3" });
      let fim = null;
      if (curto) {
        let d = "", pen = false;
        rs.forEach((r, i) => { const v = horas.get(r[0]); if (!v) { pen = false; return; }
          v.forEach((z, hh) => { if (z == null) { pen = false; return; } d += `${pen ? "L" : "M"}${xh(i, hh)},${y(z)}`; pen = true; fim = [xh(i, hh), z]; }); });
        S(svg, "path", { d, fill: "none", stroke: "var(--accent)", "stroke-width": N > 40 ? 0.9 : 1.3, "stroke-linejoin": "round" });
      } else {
        const ok = rs.map((r, i) => [i, r]).filter(([, r]) => r[6] != null && r[7] != null);
        S(svg, "path", { d: ok.map(([i, r], k) => `${k ? "L" : "M"}${xc(i)},${y(r[7])}`).join("") + [...ok].reverse().map(([i, r]) => `L${xc(i)},${y(r[6])}`).join("") + "Z", fill: "color-mix(in srgb, var(--accent) 22%, transparent)" });
        S(svg, "path", { d: rs.map((r, i) => `${i ? "L" : "M"}${xc(i)},${y(r[1])}`).join(""), fill: "none", stroke: "var(--accent)", "stroke-width": 1.2 });
        fim = [xc(N - 1), rs[N - 1][1]];
      }
      if (fim) S(svg, "text", { x: w - m.r + 6, y: y(fim[1]) + 3, class: "forte", style: "fill:var(--accent)" }, "DESSEM " + n(fim[1]));
      rs.forEach((r, i) => { const lab = rotX(r[0], i); if (lab) S(svg, "text", { x: xc(i), y: h - 6, "text-anchor": "middle", class: lab.forte ? "forte" : null }, lab.t ?? lab); });
      const foco = S(svg, "line", { y1: m.t, y2: h - m.b, stroke: "var(--ink-3)", opacity: 0 });
      rs.forEach((r, i) => {
        const a = S(svg, "rect", { x: xd(i), y: m.t, width: dw, height: h - m.t - m.b, fill: "transparent" });
        const horaDe = e => { const b = svg.getBoundingClientRect(); const px = (e.clientX - b.left) / b.width * w; return Math.max(0, Math.min(23, Math.floor((px - xd(i)) / dw * 24))); };
        a.addEventListener("pointermove", e => { const xx = curto ? xh(i, horaDe(e)) : xc(i); foco.setAttribute("x1", xx); foco.setAttribute("x2", xx); foco.setAttribute("opacity", 0.6); });
        a.addEventListener("pointerleave", () => foco.setAttribute("opacity", 0));
        const g = porDia.get(r[0]);
        dicaEm(a, e => {
          if (!curto) return `<b>${dataBr(r[0])} ${diaSem(r[0])}</b><br>PLD horário: mínimo ${n(r[6], 1)} · média ${n(r[1], 1)} · máximo ${n(r[7], 1)}`;
          const hh = horaDe(e), v = (horas.get(r[0]) || [])[hh];
          return `<b>${dataBr(r[0])} ${diaSem(r[0])} · ${hh}h</b>${VALE_H.includes(hh) ? " · vale" : PONTA_H.includes(hh) ? " · ponta" : ""}<br>PLD ${v == null ? "—" : "R$ " + n(v, 1)}${v != null && v <= r[3] + 0.005 ? " (piso)" : ""}` + (g ? `<br>${descr(g)}` : "");
        });
      });
    }

    // ---------- barras empilhadas por bloco ----------
    function legendaBlocos(id) { document.getElementById(id).innerHTML = BLOCOS.map(([, nome, cor]) => `<span><i style="background:${cor}"></i>${nome}</span>`).join("") + '<span><i class="p" style="background:var(--ink)"></i>Desvio total</span>'; }
    function empilhado(svg, rows, w, h, rotX, titulo) {
      svg.replaceChildren();
      const m = { l: 40, r: 6, t: 10, b: 24 };
      const segs = rows.map(r => { let pos = 0, neg = 0; const s = BLOCOS.map(([k, , cor]) => { const v = r[k] || 0; let a, b; if (v >= 0) { a = pos; b = pos += v; } else { a = neg; b = neg += v; } return { a, b, cor }; }); return { r, s, pos, neg }; });
      const ax = eixo(Math.min(0, ...segs.map(d => Math.min(d.neg, d.r.delta))), Math.max(0, ...segs.map(d => Math.max(d.pos, d.r.delta))));
      const y = v => m.t + (h - m.t - m.b) * (1 - (v - ax.a) / (ax.b - ax.a));
      const bw = (w - m.l - m.r) / rows.length, x = i => m.l + i * bw;
      ax.t.forEach(t => { S(svg, "line", { x1: m.l, x2: w - m.r, y1: y(t), y2: y(t), stroke: t === 0 ? "var(--ink-3)" : "var(--rule)" }); S(svg, "text", { x: m.l - 6, y: y(t) + 3, "text-anchor": "end" }, n(t)); });
      const larg = Math.max(1, bw * 0.72);
      segs.forEach((d, i) => {
        d.s.forEach(s => { if (s.a !== s.b) S(svg, "rect", { x: x(i) + (bw - larg) / 2, y: y(Math.max(s.a, s.b)), width: larg, height: Math.max(0.5, Math.abs(y(s.a) - y(s.b))), fill: s.cor, rx: Math.min(2, larg / 2), opacity: d.r.parcial ? 0.45 : null }); });
        if (d.r.parcial) { const topo = y(Math.max(d.pos, 0)), base = y(Math.min(d.neg, 0)); S(svg, "rect", { x: x(i) + (bw - larg) / 2, y: topo, width: larg, height: Math.max(1, base - topo), fill: "none", stroke: "var(--ink-2)", "stroke-dasharray": "3 2", rx: 2 }); }
        S(svg, "circle", { cx: x(i) + bw / 2, cy: y(d.r.delta), r: Math.max(1.6, Math.min(3, bw / 3)), fill: "var(--ink)", stroke: "var(--surface)", "stroke-width": 1 });
        const lab = rotX(d.r, i); if (lab) S(svg, "text", { x: x(i) + bw / 2, y: h - 6, "text-anchor": "middle", class: lab.forte ? "forte" : null }, lab.t);
        const alvo = S(svg, "rect", { x: x(i), y: m.t, width: bw, height: h - m.t - m.b, fill: "transparent" });
        dicaEm(alvo, `<b>${titulo(d.r)}</b><br>desvio ${sn(d.r.delta, 1)} R$/MWh<br>vale ${sn(d.r.vale, 1)} · ponta ${sn(d.r.ponta, 1)} · demais ${sn(d.r.demais, 1)}` + (d.r.extra || ""));
      });
    }
    legendaBlocos("leg-mes");
    let HIST = "todo", MES_DIAS = ultMes;
    abas("abas-hist", [["ano", `No ano (${ultMes.slice(0, 4)})`], ["12m", "Últimos 12 meses"], ["todo", "Todo o histórico"]], HIST, v => { HIST = v; desenharMensal(); });
    const selMes = document.getElementById("sel-mes-dias");
    selMes.addEventListener("change", () => { MES_DIAS = selMes.value; desenharMensal(); });
    function desenharMensal() {
      document.getElementById("tt-mes").textContent = `Desvio por bloco de horas · ${SUBN[SUB]}`;
      let dm = D.desvio_mensal.filter(r => r.sub === SUB).sort((a, b) => (a.mes < b.mes ? -1 : 1));
      if (HIST === "ano") dm = dm.filter(r => r.mes.startsWith(ultMes.slice(0, 4)));
      if (HIST === "12m") dm = dm.slice(-12);
      const curto = HIST !== "todo";
      empilhado(document.getElementById("g-mes"), dm.map(r => ({ ...r, extra: `<br>DECOMP ${n(r.decomp, 1)} · DESSEM ${n(r.dessem, 1)}` + (r.parcial ? `<br>mês em curso: realizado de ${r.dias} dias, até ${dataBr(ref.ultimo_dia)}` : "") })), 700, 260,
        (r, i) => (curto ? { t: rot(r.mes) + (r.parcial ? "*" : ""), forte: r.mes.endsWith("-01") } : r.mes.endsWith("-01") ? { t: r.mes.slice(0, 4), forte: true } : null), r => rotLongo(r.mes) + (r.parcial ? " (parcial)" : ""));
      const todosDias = ((D.dias_blocos || {})[SUB] || []);
      const mesesDias = [...new Set(todosDias.map(r => r.data.slice(0, 7)))].sort().reverse();
      if (!mesesDias.includes(MES_DIAS)) MES_DIAS = mesesDias[0] || ultMes;
      selMes.replaceChildren(...mesesDias.map(m => { const o = document.createElement("option"); o.value = m; o.textContent = rot(m) + (m === ultMes ? " (corrente)" : ""); o.selected = m === MES_DIAS; return o; }));
      const dd = todosDias.filter(r => r.data.startsWith(MES_DIAS)).sort((a, b) => (a.data < b.data ? -1 : 1));
      document.getElementById("tt-mes-dias").textContent = `${MESL[+MES_DIAS.slice(5, 7) - 1]} de ${MES_DIAS.slice(0, 4)}, por dia` + (MES_DIAS === ultMes ? ` · até ${dataBr(ref.ultimo_dia)}` : "");
      empilhado(document.getElementById("g-mes-dias"), dd.map(r => ({ ...r, extra: `<br>DECOMP ${n(r.decomp, 1)} · DESSEM ${n(r.dessem, 1)}` })), 350, 260,
        (r, i) => (i % Math.max(1, Math.ceil(dd.length / 8)) === 0 ? { t: r.data.slice(8, 10) } : null), r => `${dataBr(r.data)} · ${diaSem(r.data)}`);
    }


    // ---------- contribuição por faixa e tipo; contagem de horas ----------
    const PER_C = [["corrente", `Mês corrente (${rot(ultMes)})`], ["ultimo", "Último mês fechado"], ["3m", "Últimos 3 meses"], ["12m", "Últimos 12 meses"], ...Object.keys(D.contribuicao.SE).filter(k => k.startsWith("a")).map(k => [k, k.slice(1)])];
    let PERC = "3m";
    abas("abas-per-c", PER_C, PERC, v => { PERC = v; desenharContrib(); });
    // contribuição por tipo de dia × faixa (D067): conta feita no Python (publicacao.contribuicao)
    function desenharContrib() {
      const C = D.contribuicao[SUB][PERC], ms = C.meses;
      const per = ms.length ? (ms.length === 1 ? rotLongo(ms[0]) : `${rot(ms[0])} a ${rot(ms[ms.length - 1])}`) : "—";
      document.getElementById("tt-contrib").textContent = `Desvio por faixa horária e tipo de dia · ${SUBN[SUB]} · ${per}`;
      const COR = Object.fromEntries(TIPOS.map(([t, nomeT, cor]) => [t, { nomeT, cor }]));
      const linhasC = C.linhas.map(r => ({ ...r, t: r.tipo, f: r.faixa, ...COR[r.tipo] }));
      const total = C.total;
      document.getElementById("tot-c").textContent = `total ${sn(total, 1)}`;
      // contribuição
      const g1 = document.getElementById("g-contrib"); g1.replaceChildren();
      const w = 520, h = 330, m = { l: 200, r: 46, t: 6, b: 18 }, rh = (h - m.t - m.b) / linhasC.length;
      const lim = Math.max(1, ...linhasC.map(r => Math.abs(r.contrib)));
      const ax = eixo(Math.min(0, ...linhasC.map(r => r.contrib)), Math.max(0, ...linhasC.map(r => r.contrib)), 4);
      const xC = v => m.l + (w - m.l - m.r) * (v - ax.a) / (ax.b - ax.a);
      ax.t.forEach(t => { S(g1, "line", { x1: xC(t), x2: xC(t), y1: m.t, y2: h - m.b, stroke: t === 0 ? "var(--ink-3)" : "var(--rule)" }); S(g1, "text", { x: xC(t), y: h - 4, "text-anchor": "middle" }, n(t)); });
      linhasC.forEach((r, i) => {
        const yy = m.t + i * rh;
        if (i % FAIXAS.length === 0) S(g1, "text", { x: 0, y: yy + rh * 0.7, class: "forte" }, r.nomeT.replace("Domingo/feriado", "Dom./feriado"));
        S(g1, "text", { x: m.l - 6, y: yy + rh * 0.7, "text-anchor": "end" }, r.f);
        S(g1, "rect", { x: Math.min(xC(0), xC(r.contrib)), y: yy + rh * 0.18, width: Math.max(0.5, Math.abs(xC(r.contrib) - xC(0))), height: rh * 0.64, fill: r.cor, rx: 2 });
        S(g1, "text", { x: r.contrib >= 0 ? xC(r.contrib) + 4 : xC(r.contrib) - 4, y: yy + rh * 0.7, "text-anchor": r.contrib >= 0 ? "start" : "end", class: "forte" }, sn(r.contrib, 1));
        const a = S(g1, "rect", { x: 0, y: yy, width: w, height: rh, fill: "transparent" });
        dicaEm(a, `<b>${r.nomeT} · ${r.f}</b><br>contribuição ${sn(r.contrib, 1)} R$/MWh<br>desvio médio da célula ${sn(r.medio, 1)} R$/MWh<br>${n(r.dias)} dias`);
      });
      // contagem
      const g2 = document.getElementById("g-cont"); g2.replaceChildren();
      const m2 = { l: 200, r: 30, t: 6, b: 18 }, maxH = Math.max(...FAIXAS.map(f => f[1].length));
      const xH = v => m2.l + (w - m2.l - m2.r) * v / maxH;
      for (let t = 0; t <= maxH; t += 2) { S(g2, "line", { x1: xH(t), x2: xH(t), y1: m2.t, y2: h - m2.b, stroke: "var(--rule)" }); S(g2, "text", { x: xH(t), y: h - 4, "text-anchor": "middle" }, t + "h"); }
      linhasC.forEach((r, i) => {
        const yy = m2.t + i * rh;
        if (i % FAIXAS.length === 0) S(g2, "text", { x: 0, y: yy + rh * 0.7, class: "forte" }, r.nomeT.replace("Domingo/feriado", "Dom./feriado"));
        S(g2, "text", { x: m2.l - 6, y: yy + rh * 0.7, "text-anchor": "end" }, r.f);
        S(g2, "rect", { x: xH(0), y: yy + rh * 0.12, width: xH(r.nh) - xH(0), height: rh * 0.76, fill: "var(--vazio)", rx: 2 });
        S(g2, "rect", { x: xH(0), y: yy + rh * 0.12, width: xH(r.abaixo) - xH(0), height: rh * 0.36, fill: `color-mix(in srgb, ${r.cor} 45%, transparent)`, rx: 2 });
        S(g2, "rect", { x: xH(0), y: yy + rh * 0.12, width: xH(r.piso) - xH(0), height: rh * 0.36, fill: r.cor, rx: 2 });
        S(g2, "rect", { x: xH(0), y: yy + rh * 0.52, width: xH(r.acima) - xH(0), height: rh * 0.36, fill: "none", stroke: r.cor, "stroke-width": 1.2, rx: 2 });
        const a = S(g2, "rect", { x: 0, y: yy, width: w, height: rh, fill: "transparent" });
        dicaEm(a, `<b>${r.nomeT} · ${r.f}</b> (${r.nh} h por dia)<br>abaixo do DECOMP: ${n(r.abaixo, 1)} h/dia<br>no piso: ${n(r.piso, 1)} h/dia<br>acima do DECOMP: ${n(r.acima, 1)} h/dia`);
      });
    }

    // ---------- horas no piso por hora e tipo ----------
    let MEDIDA = "piso", MESH = ultMes;
    abas("abas-medida", [["piso", "No piso"], ["abaixo", "Abaixo do DECOMP"], ["acima", "Acima do DECOMP"]], MEDIDA, v => { MEDIDA = v; desenharHora(); });
    function serieHora(a, idx) { return HORAS.map(hh => [hh, a && a[hh] && a[hh][0] ? 100 * a[hh][idx] / a[hh][0] : null]); }
    function desenharHora() {
      const idx = { piso: 1, abaixo: 2, acima: 3 }[MEDIDA], nomeM = { piso: "no piso", abaixo: "abaixo do DECOMP", acima: "acima do DECOMP" }[MEDIDA];
      const H = D.horas.mensal[SUB] || {}, ms = Object.keys(H).sort();
      if (!H[MESH]) MESH = ms[ms.length - 1];
      abas("abas-mes-h", ms.slice(-13).reverse().map(m => [m, rot(m)]), MESH, v => { MESH = v; desenharHora(); });
      document.getElementById("tt-hora").textContent = `Horas ${nomeM} por hora e tipo de dia · ${SUBN[SUB]} · ${rotLongo(MESH)}`;
      const ss = TIPOS.map(([t, nome, cor]) => ({ nome, cor, pts: serieHora(H[MESH] && H[MESH][t], idx), pontos: true }));
      linhas(document.getElementById("g-hora"), { w: 1040, h: 240, xs: HORAS, series: ss, sombras: SOMBRAS, y0: 0, y1: 100, fmtY: v => v + "%", rotX: hh => hh + "h",
        dica: hh => `<b>${hh}h · ${rot(MESH)}</b><br>` + TIPOS.map(([t, nome], i) => { const a = H[MESH] && H[MESH][t] && H[MESH][t][hh]; return `${nome}: ${a && a[0] ? n(100 * a[idx] / a[0]) + "% de " + a[0] + " h" : "—"}`; }).join("<br>") });
      const Ws = (D.horas.semanal[SUB] || {})[MESH] || {}, sems = Object.keys(Ws).sort();
      const box = document.getElementById("g-semanas"); box.replaceChildren();
      document.getElementById("tt-sem-hora").textContent = `${rotLongo(MESH)} por semana operativa (revisão do DECOMP) · só os dias de cada semana que caem no mês`;
      if (!sems.length) { const p = document.createElement("p"); p.className = "leg"; p.textContent = "Sem revisões disponíveis para este mês."; box.appendChild(p); }
      sems.forEach(sm => {
        const W = Ws[sm], card = document.createElement("div"); card.className = "bloco"; card.style.padding = "8px";
        card.innerHTML = `<div class="mini-ttl"><b>RV${W.rv} · ${dataBr(sm).slice(0, 5)}</b><span>${W.dias} ${W.dias === 1 ? "dia" : "dias"}</span></div>`;
        const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 300 150"); card.appendChild(svg); box.appendChild(card);
        linhas(svg, { w: 300, h: 150, ml: 34, xs: HORAS, series: TIPOS.map(([t, , cor]) => ({ cor, pts: serieHora(W[t], idx), larg: 1.8 })), sombras: SOMBRAS, y0: 0, y1: 100, nt: 2, fmtY: v => v + "%", rotX: hh => (hh % 6 === 0 ? hh + "h" : null),
          dica: hh => `<b>RV${W.rv} · semana de ${dataBr(sm)} · ${hh}h</b><br>` + TIPOS.map(([t, nome]) => { const a = W[t] && W[t][hh]; return `${nome}: ${a && a[0] ? n(100 * a[idx] / a[0]) + "% de " + a[0] + " h" : "—"}`; }).join("<br>") });
      });
    }

    function desenharSub() { desenharMensal(); desenharContrib(); desenharHora(); desenharNivel(); }
    desenharSub();
  }

  paginaAcompanhamento();
  document.getElementById("fontes").textContent =
    `Fontes: decks do DESSEM e do DECOMP da CCEE, PLD horário publicado pela CCEE e limites do PLD de cada ano. ` +
    `Dados até ${dataBr(ref.ultimo_dia)}${notaCalc}.`;
})();
