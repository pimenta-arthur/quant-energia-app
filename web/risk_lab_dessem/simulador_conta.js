// Conta do simulador do PLD médio do mês, v1 simplificada (bloco 7): a mesma de
// qe_risk_lab_dessem.simulador.dia_s e prever_mes. Roda no navegador (o usuário digita o DECOMP e edita as
// premissas) e no teste de paridade Python × JS (tests/test_risk_lab_dessem_simulador.py, com node).
(function (raiz) {
  function criar(NV, NP) {
    const NF = 24 - NP;
    // dia típico de um tipo de dia: PLD e contribuição de cada grupo de horas ao desvio sobre o DECOMP
    function diaTipico(p, Dm, P, premio) {
      const esp = Math.max(Dm - P, 0), hh = Math.min(Math.max(p.horas_piso, 0), NV);
      const pf = Math.max(Dm + p.frac_fora * esp, P), pp = Math.max(Dm + premio, P);
      return { pld: (hh * P + (NF - hh) * pf + NP * pp) / 24, vpiso: hh * (P - Dm) / 24, fora: (NF - hh) * (pf - Dm) / 24, ponta: NP * (pp - Dm) / 24 };
    }
    // soma dos dias típicos pesados pelas partes do mês (c.parte_util, c.parte_sabado, c.parte_domingo)
    const TIPOS_SIM = [["útil", "parte_util"], ["sábado", "parte_sabado"], ["domingo/feriado", "parte_domingo"]];
    function somar(c, Dm, premissa, premio) {
      const P = c.piso;
      let tot = 0; const comp = { vpiso: 0, fora: 0, ponta: 0 }, porTipo = {};
      for (const [t, col] of TIPOS_SIM) {
        const s = c[col]; if (!s) continue;
        const d = diaTipico(premissa(t), Dm, P, premio(t));
        tot += s * d.pld; porTipo[t] = { s, ...d };
        for (const k in comp) comp[k] += s * d[k];
      }
      return { tot, pld: Math.max(tot, P), ...comp, porTipo };
    }
    return { diaTipico, somar };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { criar };
  else raiz.ContaSimulador = { criar };
})(this);
