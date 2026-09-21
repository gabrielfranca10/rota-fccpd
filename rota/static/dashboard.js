"use strict";

const ROTULOS_STATUS = { NO_PRAZO: "No prazo", EM_RISCO: "Em risco", ATRASADO: "Atrasado", ENTREGUE: "Entregue" };

// mais urgente primeiro; é a ordem dos cartões, da rosca e da legenda
const SITUACOES = [
  ["ATRASADO", "Atrasados", "passaram da hora limite", "i-atrasado"],
  ["EM_RISCO", "Em risco", "perto da hora limite", "i-risco"],
  ["NO_PRAZO", "No prazo", "dentro do combinado", "i-prazo"],
  ["ENTREGUE", "Entregues", "concluídos", "i-entregue"],
];

// tipo do alerta -> [texto para pessoas, tom da faixa]
const ROTULOS_ALERTA = {
  PEDIDO_EM_RISCO: ["Pedido em risco", "risco"],
  PEDIDO_ATRASADO: ["Pedido atrasado", "atraso"],
  PEDIDO_AGUARDANDO_ENTREGADOR: ["Aguardando entregador", "risco"],
  PEDIDO_DESPACHADO: ["Pedido despachado", "ok"],
  PEDIDO_REDESPACHADO: ["Pedido redespachado", "info"],
  PEDIDO_RECALCULADO: ["Limite recalculado", "info"],
  TRANSITO_ATUALIZADO: ["Trânsito atualizado", "info"],
  NOTIFICACAO_NAO_VINCULADA: ["Notificação sem restaurante", "atraso"],
};

const LIMITE_LINHAS = 200;
const LIMITE_URGENTES = 7;

let statusFiltro = "";
let ultimoAlertaSeq = 0;

function $(sel) {
  return document.querySelector(sel);
}

// tudo que vem da API (descrição de notificação, nomes etc.) pode conter texto arbitrário:
// nunca interpolar direto em innerHTML sem escapar.
function esc(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

async function getJSON(caminho) {
  const r = await fetch(caminho);
  if (!r.ok) throw new Error(`${caminho} -> HTTP ${r.status}`);
  return r.json();
}

function icone(id) {
  return `<svg class="icone" viewBox="0 0 24 24" aria-hidden="true"><use href="#${id}"/></svg>`;
}

function badge(status) {
  return `<span class="badge badge-${esc(status)}">${esc(ROTULOS_STATUS[status] || status)}</span>`;
}

function horaCurta(iso) {
  if (!iso) return "—";
  const m = /T(\d{2}:\d{2})/.exec(iso);
  return m ? m[1] : iso;
}

// 2026-09-21T11:32:00-03:00 -> ["21/09/2026", "11:32"]
function dataEHora(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(iso || "");
  return m ? [`${m[3]}/${m[2]}/${m[1]}`, m[4]] : [String(iso ?? "—"), ""];
}

// ped_81da0fb3f0a647609de89212a405dc86 -> ped_81da0f…
function idCurto(id) {
  const s = String(id ?? "");
  const m = /^([a-z]+_)([0-9a-f]{12,})$/i.exec(s);
  return m ? `${m[1]}${m[2].slice(0, 6)}…` : s;
}

function iniciais(nome) {
  const partes = String(nome ?? "").trim().split(/\s+/).filter(Boolean);
  if (!partes.length) return "?";
  return (partes[0][0] + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}

async function atualizarStatus() {
  try {
    await getJSON("/health");
    $("#status-ponto").className = "ponto ok";
    $("#status-texto").textContent = "Operacional";
    return true;
  } catch {
    $("#status-ponto").className = "ponto erro";
    $("#status-texto").textContent = "Sem conexão com o servidor";
    return false;
  }
}

function renderRosca(contagens, total) {
  const R = 15.9155; // circunferência = 100, então o traço é direto em porcentagem
  let acumulado = 0;
  const arcos = total === 0 ? "" : SITUACOES
    .filter(([chave]) => contagens[chave] > 0)
    .map(([chave]) => {
      const pct = (contagens[chave] / total) * 100;
      const arco = `<circle class="donut-seg tom-${chave}" cx="21" cy="21" r="${R}" fill="none" stroke-width="5"`
        + ` stroke-dasharray="${pct.toFixed(3)} ${(100 - pct).toFixed(3)}" stroke-dashoffset="${(-acumulado).toFixed(3)}"/>`;
      acumulado += pct;
      return arco;
    })
    .join("");
  $("#donut").innerHTML = `
    <svg class="donut" viewBox="0 0 42 42" role="img" aria-label="pedidos por situação">
      <circle class="donut-fundo" cx="21" cy="21" r="${R}" fill="none" stroke-width="5"/>
      <g transform="rotate(-90 21 21)">${arcos}</g>
    </svg>
    <div class="donut-centro"><b>${esc(total)}</b><span>pedidos</span></div>`;
}

function renderSituacao(contagens, metricas) {
  const linhas = SITUACOES.map(([chave, rotulo]) => `
    <li class="tom-${chave}"><span class="marca-cor"></span><span>${esc(rotulo)}</span>
      <b>${esc(contagens[chave])}</b><span class="unidade">pedidos</span></li>`);
  const aguardando = metricas.pedidos_aguardando_entregador;
  linhas.push(`
    <li class="divisor tom-EM_RISCO"><span class="marca-cor"></span><span>Aguardando entregador</span>
      <b>${esc(aguardando)}</b><span class="unidade">pedidos</span></li>`);
  linhas.push(`
    <li class="tom-NEUTRO"><span class="marca-cor"></span><span>Fila de ingestão</span>
      <b>${esc(metricas.fila_ingestao)}</b><span class="unidade">notificações</span></li>`);
  linhas.push(`
    <li class="tom-NEUTRO"><span class="marca-cor"></span><span>Trânsito</span>
      <b>v${esc(metricas.transito_versao)}</b><span class="unidade">versão</span></li>`);
  $("#situacao").innerHTML = linhas.join("");
}

function renderUrgentes(pedidos) {
  const abertos = pedidos.filter((p) => p.status !== "ENTREGUE");
  $("#contador-urgentes").textContent = abertos.length;
  const itens = abertos.slice(0, LIMITE_URGENTES).map((p) => {
    const entregador = p.entregador_responsavel_id
      ? esc(p.entregador_responsavel_id)
      : `<span class="sem-entregador">aguardando entregador</span>`;
    const pilula = p.status === "ATRASADO" ? "Atrasado" : `${p.minutos_restantes} min`;
    return `
    <li class="urgente">
      <span class="bolha tom-${esc(p.status)}">${icone("i-pacote")}</span>
      <span class="urgente-texto">
        <span class="urgente-titulo">${esc(p.numero_pedido)}<small>${esc(p.plataforma)}</small></span>
        <span class="urgente-meta">${esc(p.restaurante_id)} · limite às ${esc(horaCurta(p.hora_limite_entrega))} · ${entregador}</span>
      </span>
      <span class="pilula tom-${esc(p.status)}">${esc(pilula)}</span>
    </li>`;
  });
  $("#lista-urgentes").innerHTML = itens.join("") || `<li class="vazio">Nenhum pedido em aberto.</li>`;
}

async function atualizarKpisEPedidos() {
  const [metricas, pedidos] = await Promise.all([
    getJSON("/api/v1/metricas"),
    getJSON("/api/v1/pedidos?limite=1000"),
  ]);

  const [data, hora] = dataEHora(metricas.agora);
  $("#relogio").innerHTML = `Hoje: <b>${esc(data)}</b> · <b>${esc(hora)}</b> (hora do sistema)`;

  const contagens = { NO_PRAZO: 0, EM_RISCO: 0, ATRASADO: 0, ENTREGUE: 0 };
  for (const p of pedidos.pedidos) contagens[p.status] = (contagens[p.status] || 0) + 1;
  const total = pedidos.pedidos.length;

  $("#kpis").innerHTML = SITUACOES
    .map(([chave, rotulo, nota, icon]) => `
      <div class="kpi kpi-${chave}${contagens[chave] > 0 ? " tem" : ""}">
        <div>
          <span class="kpi-rotulo">${esc(rotulo)}</span>
          <span class="kpi-valor">${esc(contagens[chave])}</span>
          <span class="kpi-nota">${esc(nota)}</span>
        </div>
        <span class="bolha tom-${chave}">${icone(icon)}</span>
      </div>`)
    .join("");

  renderRosca(contagens, total);
  renderSituacao(contagens, metricas);
  renderUrgentes(pedidos.pedidos);

  // contagem em cada aba
  document.querySelectorAll(".aba-n").forEach((el) => {
    const chave = el.dataset.n;
    el.textContent = chave ? contagens[chave] || 0 : total;
  });

  return pedidos.pedidos;
}

function renderTabela(pedidos) {
  const filtrados = statusFiltro ? pedidos.filter((p) => p.status === statusFiltro) : pedidos;
  const linhas = filtrados
    .slice(0, LIMITE_LINHAS)
    .map((p) => {
      const semRestante = p.status === "ENTREGUE" || p.status === "ATRASADO";
      const restam = semRestante
        ? `<span class="restam-vazio">—</span>`
        : `<span class="${p.status === "EM_RISCO" ? "restam-risco" : ""}">${esc(p.minutos_restantes)} min</span>`;
      const entregador = p.entregador_responsavel_id
        ? esc(p.entregador_responsavel_id)
        : `<span class="sem-entregador">aguardando</span>`;
      return `
      <tr class="linha-${esc(p.status)}">
        <td><div class="pedido-id">
          <span class="pedido-numero">${esc(p.numero_pedido)}</span>
          <span class="pedido-plataforma">${esc(p.plataforma)}</span>
        </div></td>
        <td>${esc(p.restaurante_id)}</td>
        <td>${entregador}</td>
        <td class="num">${esc(horaCurta(p.hora_limite_entrega))}</td>
        <td class="num">${restam}</td>
        <td>${badge(p.status)}</td>
      </tr>`;
    })
    .join("");
  $("#tabela-pedidos tbody").innerHTML = linhas || `<tr><td colspan="6" class="vazio">Nenhum pedido nesse filtro.</td></tr>`;

  $("#rodape-tabela").textContent = filtrados.length > LIMITE_LINHAS
    ? `Mostrando os ${LIMITE_LINHAS} primeiros de ${filtrados.length} pedidos, ordenados pela hora limite.`
    : "";
}

async function atualizarEntregadores() {
  const { entregadores } = await getJSON("/api/v1/entregadores");
  const ordenados = [...entregadores].sort((a, b) => b.pedidos_em_aberto - a.pedidos_em_aberto);
  $("#lista-entregadores").innerHTML = ordenados
    .map((e) => {
      const cap = Number(e.capacidade) || 1;
      const uso = Number(e.pedidos_em_aberto) || 0;
      const pct = Math.min(100, Math.round((uso / cap) * 100));
      const tom = pct >= 100 ? "cheia" : "";
      return `
      <li class="entregador">
        <span class="avatar" aria-hidden="true">${esc(iniciais(e.nome))}</span>
        <span class="entregador-nome">${esc(e.nome)}<small>${esc(e.veiculo)}</small></span>
        <span class="contagem">${esc(uso)}/${esc(cap)}</span>
        <span class="barra ${tom}" role="img" aria-label="${esc(uso)} de ${esc(cap)} pedidos"><span style="width:${pct}%"></span></span>
      </li>`;
    })
    .join("") || `<li class="vazio">Nenhum entregador cadastrado.</li>`;
}

function detalheAlerta(a) {
  if (a.tipo === "PEDIDO_REDESPACHADO") return `${a.de ?? "?"} → ${a.para ?? "?"}`;
  if (a.tipo === "TRANSITO_ATUALIZADO") return `v${a.versao ?? "?"} · ${a.tipo_janela ?? ""}${a.motivo ? " · " + a.motivo : ""}`;
  if (a.tipo === "PEDIDO_DESPACHADO") return `${idCurto(a.pedido_id)} → ${a.entregador_id ?? ""}`;
  return a.numero_pedido || idCurto(a.pedido_id) || idCurto(a.notificacao_id);
}

async function atualizarAlertas() {
  const dados = await getJSON(`/api/v1/alertas?apos=${ultimoAlertaSeq}&limite=50`);
  if (!dados.alertas.length) return;
  ultimoAlertaSeq = dados.ultimo_seq;

  const lista = $("#lista-alertas");
  if (lista.querySelector(".vazio")) lista.innerHTML = "";

  const itens = dados.alertas
    .slice()
    .reverse()
    .map((a) => {
      const [rotulo, tom] = ROTULOS_ALERTA[a.tipo] || [a.tipo, "info"];
      return `
      <li class="tom-${tom}">
        <span class="alerta-tipo">${esc(rotulo)}</span>
        <span class="alerta-detalhe">${esc(detalheAlerta(a))}</span>
        <span class="alerta-quando">${esc(horaCurta(a.em))}</span>
      </li>`;
    })
    .join("");
  lista.insertAdjacentHTML("afterbegin", itens);

  // mantém a lista enxuta na tela
  const excesso = [...lista.querySelectorAll("li")].slice(30);
  excesso.forEach((el) => el.remove());
}

async function rodarAuditoria() {
  const caixa = $("#resultado-auditoria");
  caixa.textContent = "Rodando…";
  try {
    const a = await getJSON("/api/v1/auditoria");
    if (a.ok) {
      caixa.innerHTML = `<span class="selo ok">✓ Tudo certo</span>`
        + `<dl class="grade-audit">`
        + `<dt>Pedidos</dt><dd>${esc(a.pedidos)}</dd>`
        + `<dt>Em aberto</dt><dd>${esc(a.pedidos_em_aberto)}</dd>`
        + `<dt>Aguardando entregador</dt><dd>${esc(a.pedidos_aguardando_entregador)}</dd>`
        + `<dt>Trânsito</dt><dd>v${esc(a.transito_versao)}</dd>`
        + `<dt>Recálculo sequencial</dt><dd>${a.oraculo_executado ? "conferido" : "não executado"}</dd>`
        + `</dl>`;
    } else {
      caixa.innerHTML = `<span class="selo erro">✗ ${esc(a.total_violacoes)} violação(ões)</span>`
        + `<ul>${a.violacoes.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>`;
    }
  } catch {
    caixa.textContent = "Falha ao consultar a auditoria. Tente de novo.";
  }
}

async function ciclo() {
  const online = await atualizarStatus();
  if (!online) return;
  try {
    const pedidos = await atualizarKpisEPedidos();
    renderTabela(pedidos);
    await atualizarEntregadores();
    await atualizarAlertas();
  } catch (e) {
    console.error("falha ao atualizar o dashboard:", e);
  }
}

// menu lateral: destaca a seção que está na tela
function espionarSecoes() {
  const itens = [...document.querySelectorAll(".nav-item")];
  const alvos = itens.map((a) => document.querySelector(a.getAttribute("href")));
  const marcar = (indice) => itens.forEach((a, i) => a.classList.toggle("ativo", i === indice));

  itens.forEach((a, i) => a.addEventListener("click", () => marcar(i)));

  // a seção atual é a última cujo topo já passou de 35% da altura da janela
  let agendado = false;
  const atualizar = () => {
    agendado = false;
    let atual = 0;
    alvos.forEach((el, i) => {
      if (el && el.getBoundingClientRect().top <= window.innerHeight * 0.35) atual = i;
    });
    marcar(atual);
  };
  window.addEventListener("scroll", () => {
    if (!agendado) { agendado = true; requestAnimationFrame(atualizar); }
  }, { passive: true });
}

document.querySelectorAll(".aba").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".aba").forEach((b) => b.classList.remove("ativa"));
    btn.classList.add("ativa");
    statusFiltro = btn.dataset.status;
    ciclo();
  });
});

$("#btn-auditoria").addEventListener("click", rodarAuditoria);

espionarSecoes();
ciclo();
setInterval(ciclo, 4000);
