// Conta da página do descolamento que depende da curva do SE digitada: a mesma de qe_pricing_descolamento.conta
// (resolver a curva do ano ao mês, descolamento exato do modelo por mês e cenário, preço justo e faixa por produto).
// Roda no navegador e no teste de paridade Python × JS (tests/test_pricing_descolamento_pagina.py, com node).
// O modelo por cenário: d = −Σ_h c_h · max(SE · perfil_h − piso, 0) (coeficientes publicados pelo Python).
(function (raiz) {
  function criar(M, SAZ) {
    // M: [{mes, horas, piso, perfil[24], cen[{id, peso, cNE, cN, trava, k}]}]; SAZ: SE do mês ÷ média do ano (12)
    const IDX = Object.fromEntries(M.map((m, i) => [m.mes, i]));
    const ano = p => +p.slice(0, 4), mesN = p => +p.slice(5, 7);
    const ANOS = [...new Set(M.map(m => ano(m.mes)))];
    const horas = ms => ms.reduce((a, p) => a + M[IDX[p]].horas, 0);

    // períodos de cada ano dentro do horizonte (chaves: A2027, S2027-1, T2027-3, M2027-05)
    function periodosDoAno(y) {
      const ms = M.filter(m => ano(m.mes) === y).map(m => m.mes);
      const S = [1, 2].map(s => ({ k: `S${y}-${s}`, s, meses: ms.filter(p => (mesN(p) <= 6) === (s === 1)) }));
      const T = [1, 2, 3, 4].map(t => ({ k: `T${y}-${t}`, t, sem: t <= 2 ? 1 : 2, meses: ms.filter(p => Math.ceil(mesN(p) / 3) === t) }));
      return { y, k: `A${y}`, meses: ms, S, T };
    }
    const PER = ANOS.map(periodosDoAno);

    // resolução da curva: cada nó vale o digitado ou o derivado do pai; filhos não digitados dividem o que falta
    // para fechar a média do pai (ponderada por horas), na proporção da sazonalidade (plana = iguais)
    function resolver(ENT, sazModo) {
      const fatorSaz = ms => { if (sazModo !== "hist") return 1; let a = 0, h = 0; ms.forEach(p => { const hh = M[IDX[p]].horas; a += SAZ[mesN(p) - 1] * hh; h += hh; }); return a / h; };
      const se = {}, info = {}, avisos = [];
      function no(chave, ms, herdado, filhos) {
        const dig = ENT[chave];
        const v = dig != null ? dig : herdado;
        info[chave] = { v: v == null ? null : v, digitado: dig != null };
        if (!filhos) { if (v != null) ms.forEach(p => { se[p] = v; }); return; }
        const vivos = filhos.filter(f => f.meses.length);
        const fixos = vivos.filter(f => ENT[f.chave] != null), livres = vivos.filter(f => ENT[f.chave] == null);
        const herdF = {};
        if (v != null) {
          const H = horas(ms), Hf = fixos.reduce((a, f) => a + horas(f.meses) * ENT[f.chave], 0);
          const Hl = livres.reduce((a, f) => a + horas(f.meses), 0);
          if (livres.length) {
            const alvo = (v * H - Hf) / Hl;
            const norm = livres.reduce((a, f) => a + fatorSaz(f.meses) * horas(f.meses), 0) / Hl;
            livres.forEach(f => { herdF[f.chave] = alvo * fatorSaz(f.meses) / norm; });
          } else if (Math.abs(Hf / H - v) > 0.05) {
            avisos.push({ tipo: "media", chave, media: Hf / H, v });
          }
        }
        vivos.forEach(f => no(f.chave, f.meses, herdF[f.chave], f.filhos));
      }
      PER.forEach(a => {
        const meses = p => ({ chave: `M${p}`, meses: [p] });
        const tri = a.T.map(t => ({ chave: t.k, meses: t.meses, filhos: t.meses.map(meses) }));
        const sem = a.S.map((s, i) => ({ chave: s.k, meses: s.meses, filhos: tri.filter((t, j) => a.T[j].sem === i + 1) }));
        no(a.k, a.meses, undefined, sem);
      });
      // valor informativo dos nós sem valor próprio: média dos meses, quando todos definidos
      PER.forEach(a => [{ k: a.k, meses: a.meses }, ...a.S, ...a.T].forEach(p => {
        if (!p.meses.length) return;
        if (info[p.k] && info[p.k].v == null && p.meses.every(q => se[q] != null))
          info[p.k] = { v: p.meses.reduce((s, q) => s + se[q] * M[IDX[q]].horas, 0) / horas(p.meses), digitado: false, media: true };
      }));
      Object.keys(se).sort().forEach(p => { if (se[p] < M[IDX[p]].piso) avisos.push({ tipo: "piso", mes: p, v: se[p], piso: M[IDX[p]].piso }); });
      return { se, info, avisos };
    }

    // descolamento exato do modelo por mês e cenário; `ajuste` aplica o choque no SE
    function calcular(se, ajuste = x => x) {
      const res = {};
      M.forEach(m => {
        const s = se[m.mes]; if (s == null) return;
        const S = ajuste(s), fol = m.perfil.map(r => Math.max(S * r - m.piso, 0));
        const cen = m.cen.map(c => ({ id: c.id, peso: c.peso, NE: -c.cNE.reduce((a, v, h) => a + v * fol[h], 0), N: -c.cN.reduce((a, v, h) => a + v * fol[h], 0), trava: c.trava, k: c.k }));
        const W = cen.reduce((a, c) => a + c.peso, 0), med = f => cen.reduce((a, c) => a + c.peso * c[f], 0) / W;
        res[m.mes] = { se: S, NE: med("NE"), N: med("N"), trava: med("trava"), cen,
          NEmin: Math.min(...cen.map(c => c.NE)), NEmax: Math.max(...cen.map(c => c.NE)), Nmin: Math.min(...cen.map(c => c.N)), Nmax: Math.max(...cen.map(c => c.N)) };
      });
      return res;
    }
    // produto: justo = média por mês (ponderada por horas) da média dos cenários; faixa = mín–máx dos cenários
    // agregados no período, só os presentes em todos os meses
    function agregar(res, ms) {
      if (!ms.length || ms.some(p => !res[p])) return null;
      const H = horas(ms), wm = p => M[IDX[p]].horas / H, out = { se: 0, NE: 0, N: 0, trava: 0 };
      ms.forEach(p => ["se", "NE", "N", "trava"].forEach(f => { out[f] += res[p][f] * wm(p); }));
      const ids = res[ms[0]].cen.map(c => c.id).filter(id => ms.every(p => res[p].cen.some(c => c.id === id)));
      const porCen = ids.map(id => { const o = { NE: 0, N: 0 }; ms.forEach(p => { const c = res[p].cen.find(x => x.id === id); o.NE += c.NE * wm(p); o.N += c.N * wm(p); }); return o; });
      if (porCen.length) { out.NEmin = Math.min(...porCen.map(c => c.NE)); out.NEmax = Math.max(...porCen.map(c => c.NE)); out.Nmin = Math.min(...porCen.map(c => c.N)); out.Nmax = Math.max(...porCen.map(c => c.N)); }
      return out;
    }
    // por ano climático: cada cenário agregado no período (nos meses em que existe)
    function porAno(res, ms, sub, pld) {
      const ids = [...new Set(ms.flatMap(p => res[p].cen.map(c => c.id)))];
      return ids.map(id => {
        const presentes = ms.filter(p => res[p].cen.some(c => c.id === id)), Hp = horas(presentes);
        const v = presentes.reduce((a, p) => { const c = res[p].cen.find(x => x.id === id); return a + ((pld ? res[p].se : 0) + c[sub]) * M[IDX[p]].horas / Hp; }, 0);
        return { ano: id, v, parcial: presentes.length < ms.length, meses: presentes };
      }).sort((a, b) => a.ano.localeCompare(b.ano));
    }
    return { IDX, ANOS, PER, horas, resolver, calcular, agregar, porAno };
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { criar };
  else raiz.ContaDescolamento = { criar };
})(this);
