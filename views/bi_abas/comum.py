"""Componentes compartilhados pelas abas do dashboard de BI."""
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import bi_service as bi
from services import fluxo_caixa_service as fluxo
from services import tesouraria_service as tesouraria
from utils.datas import hoje
from utils.formatacao import fmt_data, fmt_inteiro, fmt_pct

_TTL_SEGUNDOS = 120


def _com_cache(funcao):
    return st.cache_data(ttl=_TTL_SEGUNDOS, show_spinner=False)(funcao)


# Consultas ao banco com cache curto: o painel reconsulta o banco a cada 2 minutos
# ou quando o botão "Atualizar" é usado.
indicadores = _com_cache(bi.indicadores)
serie = _com_cache(bi.serie)
vendas_por_forma_pagamento = _com_cache(bi.vendas_por_forma_pagamento)
vendas_por_vendedor = _com_cache(bi.vendas_por_vendedor)
vendas_por_dia_semana = _com_cache(bi.vendas_por_dia_semana)
vendas_por_parcelas = _com_cache(bi.vendas_por_parcelas)
faixas_desconto = _com_cache(bi.faixas_desconto)
top_clientes = _com_cache(bi.top_clientes)
ranking_produtos = _com_cache(bi.ranking_produtos)
vendas_por_categoria = _com_cache(bi.vendas_por_categoria)
vendas_por_tamanho = _com_cache(bi.vendas_por_tamanho)
vendas_por_cor = _com_cache(bi.vendas_por_cor)
posicao_estoque = _com_cache(bi.posicao_estoque)
giro_por_sku = _com_cache(bi.giro_por_sku)
situacao_contas = _com_cache(bi.situacao_contas)
clientes_em_atraso = _com_cache(bi.clientes_em_atraso)
despesas_por_categoria = _com_cache(bi.despesas_por_categoria)
devolucoes_por_motivo = _com_cache(bi.devolucoes_por_motivo)
produtos_mais_devolvidos = _com_cache(bi.produtos_mais_devolvidos)
compras_por_fornecedor = _com_cache(bi.compras_por_fornecedor)
compras_serie = _com_cache(bi.compras_serie)
primeira_data_com_dados = _com_cache(bi.primeira_data_com_dados)
fluxo_realizado = _com_cache(fluxo.realizado)
fluxo_projetado = _com_cache(fluxo.projetado)
contas_financeiras = _com_cache(tesouraria.listar_contas)

PERIODOS = {
    "7": "Últimos 7 dias",
    "30": "Últimos 30 dias",
    "90": "Últimos 90 dias",
    "180": "Últimos 6 meses",
    "365": "Últimos 12 meses",
    "mes": "Mês atual",
    "ano": "Ano atual",
    "custom": "Personalizado",
}
_AGRUPAMENTOS = {"auto": "Automático", **bi.AGRUPAMENTOS}


def _intervalo(preset: str) -> tuple[date, date]:
    fim = hoje()
    if preset == "mes":
        return fim.replace(day=1), fim
    if preset == "ano":
        return fim.replace(month=1, day=1), fim
    return fim - timedelta(days=int(preset) - 1), fim


def seletor_periodo() -> tuple[date, date, str]:
    """Filtro de período e agrupamento exibido no topo. Devolve (início, fim, agrupamento)."""
    c1, c2, c3, c4 = st.columns([2, 2, 1.5, 1])
    preset = c1.selectbox("Período", list(PERIODOS), format_func=lambda p: PERIODOS[p], index=2, key="bi_periodo")
    if preset == "custom":
        a, b = c2.columns(2)
        inicio = a.date_input("De", value=hoje() - timedelta(days=89), max_value=hoje(), format="DD/MM/YYYY", key="bi_de")
        fim = b.date_input("Até", value=hoje(), max_value=hoje(), format="DD/MM/YYYY", key="bi_ate")
    else:
        inicio, fim = _intervalo(preset)
        c2.markdown(f"**{fmt_data(inicio)} a {fmt_data(fim)}**")
    escolha = c3.selectbox(
        "Agrupar por", list(_AGRUPAMENTOS), format_func=lambda a: _AGRUPAMENTOS[a], key="bi_agrupamento"
    )
    if c4.button("Atualizar", icon=":material/refresh:", key="bi_atualizar", help="Consulta o banco novamente"):
        st.cache_data.clear()
        st.rerun()
    if fim < inicio:
        st.error("A data final não pode ser anterior à inicial.")
        st.stop()
    agrupamento = bi.agrupamento_sugerido(inicio, fim) if escolha == "auto" else escolha
    dias = (fim - inicio).days + 1
    st.caption(
        f"{dias} dia(s) analisados, agrupados por {bi.AGRUPAMENTOS[agrupamento].lower()}. "
        "Os dados vêm direto do banco e são reconsultados a cada 2 minutos."
    )
    return inicio, fim, agrupamento


def pct_variacao(atual, anterior) -> str | None:
    """Texto da variação entre períodos para st.metric; None quando não há base de comparação."""
    resultado = bi.variacao(Decimal(atual), Decimal(anterior))
    return None if resultado is None else fmt_pct(resultado, 1, sinal=True)


def rotulo_periodo(periodo: date, agrupamento: str) -> str:
    return periodo.strftime("%m/%Y") if agrupamento == "month" else periodo.strftime("%d/%m")


def barras_horizontais(rotulos: list[str], valores: list, nome: str, altura: int | None = None) -> None:
    """Ranking em barras horizontais, da maior para a menor."""
    dados = pd.DataFrame({nome: [float(v) for v in valores]}, index=rotulos)
    st.bar_chart(dados, horizontal=True, sort=f"-{nome}", height=altura or max(160, 36 * len(rotulos) + 40))


def tabela(linhas: list[dict]) -> None:
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")


def sem_dados(mensagem: str = "Não há dados no período selecionado.") -> None:
    st.info(mensagem)


def fmt_dias(valor) -> str:
    return "-" if valor is None else f"{fmt_inteiro(round(float(valor)))} dias"
