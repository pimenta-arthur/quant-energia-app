/* Padrão visual Quant Energia · v1.1 · 2026-10 · graficos.js
   Funções pequenas para gráficos em SVG e textos em pt-BR, sem biblioteca. Regras de uso em GUIA.md.
   Carregar antes do script da página: <script src="../padrao/graficos.js"></script>
   A página precisa de <div class="dica" id="dica" hidden></div> para os tooltips (dicaEm). */

const NS_SVG = "http://www.w3.org/2000/svg";
const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESL = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

// ---------- textos ----------
/** "2026-10" → "out/26" */
const rot = p => `${MES[+p.slice(5, 7) - 1]}/${p.slice(2, 4)}`;
/** "2026-10" → "outubro de 2026" */
const rotLongo = p => `${MESL[+p.slice(5, 7) - 1]} de ${p.slice(0, 4)}`;
/** "2026-10-09…" → "09/10/26" */
const dataBr = s => `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(2, 4)}`;
/** "2026-10-09T22:55:36" → "09/10/26 22:55" */
const dataHoraBr = s => dataBr(s) + (s.length > 10 ? " " + s.slice(11, 16) : "");
/** número pt-BR com c casas; vazio ou inválido → "—" */
const n = (v, c = 0) => (v == null || !isFinite(v) ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }));
/** número com sinal (+3, −0,05, 0) */
const sn = (v, c = 0) => (v == null || !isFinite(v) ? "—" : (v > 1e-7 ? "+" : v < -1e-7 ? "−" : "") + n(Math.abs(v), c));
/** fração → "72%" */
const pct = v => (v == null || !isFinite(v) ? "—" : n(v * 100) + "%");

// ---------- SVG ----------
/** cria um elemento SVG dentro de `pai`; atributos vazios (null/undefined) são ignorados */
function S(pai, tag, at = {}, txt) {
  const e = document.createElementNS(NS_SVG, tag);
  for (const k in at) if (at[k] != null) e.setAttribute(k, at[k]);
  if (txt != null) e.textContent = txt;
  pai.appendChild(e);
  return e;
}

/** tooltip que segue o ponteiro; `txt` pode ser HTML ou função(evento) → HTML.
 *  Fica à direita e abaixo do ponteiro; perto da borda direita ou de baixo da tela, troca de lado (v1.1). */
function dicaEm(el, txt) {
  const dica = document.getElementById("dica");
  el.addEventListener("pointermove", e => {
    dica.innerHTML = typeof txt === "function" ? txt(e) : txt;
    dica.hidden = false;
    dica.style.transform = "none";
    const w = dica.offsetWidth, h = dica.offsetHeight;
    const x = e.clientX + 12 + w > innerWidth - 8 ? e.clientX - 12 - w : e.clientX + 12;
    const y = e.clientY + 12 + h > innerHeight - 8 ? e.clientY - 12 - h : e.clientY + 12;
    dica.style.left = Math.max(8, x) + "px";
    dica.style.top = Math.max(8, y) + "px";
  });
  el.addEventListener("pointerleave", () => { dica.hidden = true; });
}

// ---------- eixos ----------
/** marcas a cada `k` entre lo e hi (ex.: marcas(0, 520, 100) → 0, 100, …, 500) */
const marcas = (lo, hi, k) => { const s = []; for (let t = Math.ceil(lo / k) * k; t <= hi + 1e-9; t += k) s.push(+t.toFixed(6)); return s; };
/** passo "redondo" (1, 2 ou 5 × 10^n) para ter cerca de `alvo` marcas entre lo e hi */
const passo = (lo, hi, alvo = 5) => { const r = (hi - lo) / alvo || 1, p = Math.pow(10, Math.floor(Math.log10(r))), f = r / p; return (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p; };
/** eixo com limites arredondados: { a, b, t } (início, fim, marcas). `justo` arredonda a 1/4 do passo */
function eixo(lo, hi, alvo = 5, justo = false) {
  if (hi - lo < 1e-9) hi = lo + 1;
  const s = passo(lo, hi, alvo), f = justo ? s / 4 : s;
  const a = Math.floor(lo / f) * f, b = Math.ceil(hi / f) * f, t = [];
  for (let v = Math.ceil(a / s) * s; v <= b + 1e-9; v += s) t.push(+v.toFixed(6));
  return { a, b, t };
}
/** meses que levam rótulo num eixo de tempo estreito: só jan e jul */
const rotuloDeMes = p => /-(01|07)$/.test(p);

// ---------- rótulos e cores ----------
/** afasta para cima rótulos de texto que se encostam (lista de { el, x, y }, na ordem de prioridade) */
function empilharRotulos(rotulos, largura = 46, altura = 12) {
  const postos = [];
  rotulos.forEach(r => {
    let y = r.y;
    while (postos.some(q => Math.abs(q.x - r.x) < largura && Math.abs(q.y - y) < altura)) y -= altura;
    r.el.setAttribute("y", y);
    postos.push({ x: r.x, y });
  });
}
/** fundo divergente para erros: azul acima de zero, vermelho abaixo, mais forte quanto maior |e| / escala */
const fundoErro = (e, escala) => {
  const f = Math.round(Math.min(1, Math.abs(e) / escala) * 70);
  return `color-mix(in srgb, ${e >= 0 ? "var(--accent)" : "var(--v1)"} ${f}%, var(--vazio))`;
};
