// Conta da cotação de compra e venda do descolamento: a mesma de qe_pricing_descolamento.compra_venda.precificar (Python)
// e da pesquisa (compra_venda_conta.js, leva promocao-quant-v5). Roda no navegador e no teste de paridade Python × JS
// (tests/test_pricing_descolamento_compra_venda.py, com node).
// - método "combinado": o mais conservador entre o quantil (p) e a cauda (α, λ) em cada lado; cada lado com os seus parâmetros;
// - venda ancorada no realizado: mês a mês, o máximo entre a venda do modelo e o maior descolamento já realizado no mês;
// - swap: spread entre duas pernas (uma no SE: cotação deslocada pela diferença de SE; NE × N: ano climático a ano climático).
(function (raiz) {
  "use strict";
  const CVC = (function () {
    // quantil com interpolação linear, igual ao numpy.quantile padrão
    function quantil(x, q) {
      const s = [...x].sort((a, b) => a - b), pos = q * (s.length - 1), lo = Math.floor(pos), hi = Math.ceil(pos);
      return s[lo] + (s[hi] - s[lo]) * (pos - lo);
    }
    const media = x => x.reduce((a, b) => a + b, 0) / x.length;
    // método "quantil": compra = min(q_p, E), venda = max(q_{1−p}, E)
    function viaQuantil(x, p) { const e = media(x); return { compra: Math.min(quantil(x, p), e), venda: Math.max(quantil(x, 1 - p), e) }; }
    // método "cauda": compra = E − λ·(E − ES_inf), venda = E + λ·(ES_sup − E); ES = média dos α piores cenários de cada lado
    function viaCauda(x, alfa, lam) {
      const s = [...x].sort((a, b) => a - b), e = media(s), n = Math.max(1, Math.ceil(alfa * s.length));
      return { compra: e - lam * (e - media(s.slice(0, n))), venda: e + lam * (media(s.slice(-n)) - e) };
    }
    // "combinado": o mais conservador dos dois em cada lado
    function precificar(amostra, par) {
      const x = amostra.filter(v => v != null && isFinite(v));
      const q = viaQuantil(x, par.p), c = viaCauda(x, par.alfa, par.lam);
      return { justo: media(x), compra: Math.min(q.compra, c.compra), venda: Math.max(q.venda, c.venda) };
    }
    // cotação de um lado, com os parâmetros dele
    function cotarLado(amostra, lado, par) { return precificar(amostra, par)[lado]; }
    // venda ancorada no realizado (mês a mês): máximo entre a venda do modelo no mês e o histórico do mês (R$/MWh, já × folga);
    // sem histórico no mês, vale o modelo. O produto é a média dos meses ponderada por horas. `meses` = [{h, anos[], hist|null}]
    function vendaMensal(m, par, ancora) { const base = precificar(m.anos, par).venda; return ancora && m.hist != null ? Math.max(base, m.hist) : base; }
    function vendaProduto(meses, par, ancora) {
      const H = meses.reduce((a, m) => a + m.h, 0);
      return meses.reduce((a, m) => a + m.h * vendaMensal(m, par, ancora), 0) / H;
    }
    // swap: recebe a perna R e paga a perna P; spread = PLD_R − k·PLD_P, com k = (volume·horas pagos) ÷ (volume·horas recebidos).
    // Quem compra o swap a X ganha spread − X; quem vende, X − spread. Compra = spread baixo; venda = spread alto.
    // Uma perna é o SE (constante, curva da mesa) e a outra é NE ou N (SE da perna + descolamento d = {compra, justo, venda}).
    function swapComSE(recebeS, seS, d, seSE, k) {
      if (recebeS) return { compra: seS + d.compra - k * seSE, justo: seS + d.justo - k * seSE, venda: seS + d.venda - k * seSE };
      // paga a perna NE/N: o spread cai quando o descolamento sobe, então a compra do swap usa a venda do descolamento
      return { compra: seSE - k * (seS + d.venda), justo: seSE - k * (seS + d.justo), venda: seSE - k * (seS + d.compra) };
    }
    // pernas que variam por ano climático (NE × N, ou o mesmo submercado em períodos diferentes): spread ano a ano (D045)
    // e a política de risco de cada lado sobre a distribuição do spread. xRec e xPag = PLD de cada perna por ano climático.
    function swapVetor(xRec, xPag, k, parCompra, parVenda) {
      const s = xRec.map((v, i) => v - k * xPag[i]);
      return { compra: cotarLado(s, "compra", parCompra), justo: media(s), venda: cotarLado(s, "venda", parVenda) };
    }
    return { quantil, viaQuantil, viaCauda, precificar, cotarLado, vendaMensal, vendaProduto, swapComSE, swapVetor };
  })();

  if (typeof module !== "undefined" && module.exports) module.exports = CVC;
  else raiz.CVC = CVC;
})(this);
