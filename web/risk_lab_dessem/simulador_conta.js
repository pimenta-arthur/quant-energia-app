// Conta do simulador do PLD médio do mês, v1 simplificada (bloco 7): a mesma de
// qe_risk_lab_dessem.simulador (dia_s, prever_mes, resumo_mesa, dias_mes). Roda no navegador (o usuário digita o
// DECOMP e edita as premissas) e no teste de paridade Python × JS (tests/test_risk_lab_dessem_simulador.py, com node).
(function (raiz) {
  function criar(NV, NP, LIMIAR = 5, ESPACO_MIN = 20, REGIME = "2025-03") {
    const NF = 24 - NP;
    // dia típico de um tipo de dia: PLD e contribuição de cada grupo de horas ao desvio sobre o DECOMP
    function diaTipico(p, Dm, P, premio) {
      const esp = Math.max(Dm - P, 0), hh = Math.min(Math.max(p.horas_piso, 0), NV);
      const pf = Math.max(Dm + p.frac_fora * esp, P), pp = Math.max(Dm + premio, P);
      return { pld: (hh * P + (NF - hh) * pf + NP * pp) / 24, vpiso: hh * (P - Dm) / 24, fora: (NF - hh) * (pf - Dm) / 24, ponta: NP * (pp - Dm) / 24, horas_piso: hh, outras_horas: pf, preco_ponta: pp };
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
    const classe = d => (d < -LIMIAR ? "desconto" : d > LIMIAR ? "prêmio" : "neutro");

    // resumo para a mesa (D091): números e condições; `prem` = premissas por tipo, `premio` / `premioSens` = prêmio
    // da ponta efetivo por tipo (previsto e cenário de estresse), `pct` = % dos dias úteis no estresse
    function resumo(D, c, Dm, prem, premio, premioSens, pct, editado = false) {
      const P = c.piso, h = c.h;
      const r = somar(c, Dm, t => prem[t], t => premio[t]), cen = somar(c, Dm, t => prem[t], t => premioSens[t]);
      const pld = r.pld, delta = pld - Dm, dir = classe(delta);
      const e = D.confianca.find(x => x.h === h);
      const absTot = Math.abs(r.vpiso) + Math.abs(r.fora) + Math.abs(r.ponta) || 1;
      const bt = D.backtest.filter(x => x.h === h).sort((a, b) => (a.mes < b.mes ? -1 : 1));
      const prevReg = bt.filter(x => x.mes >= REGIME && x.direcao_prevista === dir), prevTodo = bt.filter(x => x.direcao_prevista === dir);
      const erro = Object.fromEntries((D.desempenho || []).map(x => [x.h, x.erro]));
      const p12 = Object.fromEntries(TIPOS_SIM.map(([t]) => [t, (((D.ponta_janelas || {})[t] || {}).ref12 || {}).premio ?? null]));
      const pld12 = Math.max(somar(c, Dm, t => prem[t], t => (p12[t] != null ? p12[t] : premio[t])).tot, P);
      const ph = D.piso_hist || [], esp = Dm - P;
      const mx = ph.reduce((a, x) => (a == null || x.delta > a.delta ? x : a), null);
      const pj = premio["útil"], pu12 = p12["útil"];
      return {
        mes: c.mes, antecedencia_meses: h, decomp: Dm, piso: P, pld_previsto: pld, desvio: delta, direcao: dir,
        faixa_10_90: [Math.max(pld - e.erro_p90, P), pld - e.erro_p10],
        direcao_hist: {
          pouco_historico: prevReg.length < 5,
          previsoes_desde_mar25: prevReg.length, acertos_desde_mar25: prevReg.filter(x => x.direcao_real === dir).length,
          previsoes_desde_jul24: prevTodo.length, acertos_desde_jul24: prevTodo.filter(x => x.direcao_real === dir).length,
          meses_com_a_direcao: bt.filter(x => x.direcao_real === dir).map(x => x.mes), meses_total: bt.length,
        },
        erro_medio: { antecedencia: erro[h] ?? null, um_mes: erro[1] ?? null, apos_rv0: erro[Math.max(h - 1, 1)] ?? null },
        de_onde_vem: Object.fromEntries(["vpiso", "fora", "ponta"].map(g => [g, { valor: r[g], peso: Math.abs(r[g]) / absTot }])),
        pld_ponta_na_media_12m: pld12,
        premio_ponta: { janela: { ...premio }, media_12m: p12 },
        alertas: {
          decomp_perto_do_piso: esp < ESPACO_MIN,
          historico_no_piso: esp < 5 && ph.length ? { meses: ph.length, media: ph.reduce((a, x) => a + x.delta, 0) / ph.length, max: mx.delta, mes_max: mx.mes, previsao_acima_de_todos: delta > mx.delta } : null,
          ponta_afastada_da_media_12m: pu12 != null && Math.abs(pj - pu12) > Math.max(50, 0.5 * Math.abs(pu12)),
          premissas_editadas: editado,
        },
        sensibilidade: { preco_ponta_util: Math.max(Dm + premioSens["útil"], P), pct_dias_uteis: pct, pld: Math.max((1 - pct / 100) * r.tot + pct / 100 * cen.tot, P) },
        // para desenhar (não entram na paridade)
        _r: r,
      };
    }

    // dias do mês (D095): cada dia recebe o dia típico do seu tipo (c.dias: u útil, s sábado, d domingo, f feriado)
    const TIPO_COD = { u: "útil", s: "sábado", d: "domingo/feriado", f: "domingo/feriado" };
    const NOME_COD = { u: "útil", s: "sábado", d: "domingo", f: "feriado" };
    const DSEM = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
    function diasMes(c, Dm, prem, premio, premioSens, pct) {
      const P = c.piso, [y, mm] = c.mes.split("-").map(Number);
      return [...(c.dias || "")].map((cod, i) => {
        const t = TIPO_COD[cod], base = diaTipico(prem[t], Dm, P, premio[t]), est = diaTipico(prem[t], Dm, P, premioSens[t]);
        return {
          data: `${y}-${String(mm).padStart(2, "0")}-${String(i + 1).padStart(2, "0")}`, dia: DSEM[new Date(Date.UTC(y, mm - 1, i + 1)).getUTCDay()], tipo: NOME_COD[cod],
          horas_piso: base.horas_piso, outras_horas: base.outras_horas, ponta: base.preco_ponta, pld_dia: base.pld,
          pld_dia_ponta_estressada: cod === "u" ? est.pld : null,
          pld_dia_esperado_com_pct: cod === "u" ? (1 - pct / 100) * base.pld + pct / 100 * est.pld : base.pld,
          _cod: cod, _ponta_est: est.preco_ponta,
        };
      });
    }
    return { diaTipico, somar, classe, resumo, diasMes };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { criar };
  else raiz.ContaSimulador = { criar };
})(this);
