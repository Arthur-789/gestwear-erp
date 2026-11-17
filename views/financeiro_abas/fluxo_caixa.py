"""Aba Fluxo de caixa: realizado (movimentações) e projetado (contas em aberto)."""
from datetime import timedelta

import pandas as pd
import streamlit as st

from services import fluxo_caixa_service as fluxo
from services import tesouraria_service as tesouraria
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje
from utils.formatacao import fmt_brl

_VERDE, _VERMELHO = "#2e7d32", "#c62828"


def _rotulo(periodo, agrupamento: str) -> str:
    return periodo.strftime("%d/%m/%Y") if agrupamento == "day" else periodo.strftime("%m/%Y")


def _graficos(periodos: list[dict], colunas: dict[str, str]) -> None:
    """colunas: chave do período -> nome exibido (entradas/saídas ou a receber/a pagar)."""
    indice = pd.to_datetime([p["periodo"] for p in periodos])
    barras = pd.DataFrame(
        {nome: [float(p[chave]) for p in periodos] for chave, nome in colunas.items()}, index=indice
    )
    st.bar_chart(barras, color=[_VERDE, _VERMELHO], stack=False)
    saldo = pd.DataFrame({"Saldo acumulado": [float(p["saldo_acumulado"]) for p in periodos]}, index=indice)
    st.line_chart(saldo)


def _tabela(periodos: list[dict], colunas: dict[str, str], agrupamento: str) -> None:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Período": _rotulo(p["periodo"], agrupamento),
                    **{nome: fmt_brl(p[chave]) for chave, nome in colunas.items()},
                    "Saldo do período": fmt_brl(p["saldo_periodo"]),
                    "Saldo acumulado": fmt_brl(p["saldo_acumulado"]),
                }
                for p in periodos
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def _realizado() -> None:
    contas = {c["id"]: c["nome"] for c in tesouraria.listar_contas()}
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    conta_id = c1.selectbox(
        "Conta", [None] + list(contas),
        format_func=lambda i: "Todas" if i is None else contas[i], key="fx_r_conta",
    )
    inicio = c2.date_input("De", value=hoje() - timedelta(days=29), format="DD/MM/YYYY", key="fx_r_de")
    fim = c3.date_input("Até", value=hoje(), format="DD/MM/YYYY", key="fx_r_ate")
    agrupamento = c4.radio(
        "Agrupar por", list(fluxo.AGRUPAMENTOS), format_func=lambda a: fluxo.AGRUPAMENTOS[a],
        horizontal=True, key="fx_r_agrup",
    )
    try:
        dados = fluxo.realizado(inicio, fim, agrupamento, conta_id)
    except RegraDeNegocioError as e:
        st.warning(str(e))
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo inicial", fmt_brl(dados["saldo_inicial"]))
    m2.metric("Entradas", fmt_brl(dados["total_entradas"]))
    m3.metric("Saídas", fmt_brl(dados["total_saidas"]))
    m4.metric("Saldo final", fmt_brl(dados["saldo_final"]))
    colunas = {"entradas": "Entradas", "saidas": "Saídas"}
    _graficos(dados["periodos"], colunas)
    _tabela(dados["periodos"], colunas, agrupamento)


def _projetado() -> None:
    c1, c2 = st.columns([1, 1])
    fim = c1.date_input(
        "Projetar até", value=hoje() + timedelta(days=30), min_value=hoje(), format="DD/MM/YYYY", key="fx_p_ate"
    )
    agrupamento = c2.radio(
        "Agrupar por", list(fluxo.AGRUPAMENTOS), format_func=lambda a: fluxo.AGRUPAMENTOS[a],
        horizontal=True, key="fx_p_agrup",
    )
    try:
        dados = fluxo.projetado(fim, agrupamento)
    except RegraDeNegocioError as e:
        st.warning(str(e))
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo atual", fmt_brl(dados["saldo_inicial"]))
    m2.metric("A receber", fmt_brl(dados["total_receber"]))
    m3.metric("A pagar", fmt_brl(dados["total_pagar"]))
    m4.metric("Saldo projetado", fmt_brl(dados["saldo_final"]))
    if dados["atraso_receber"] or dados["atraso_pagar"]:
        st.caption(
            f"Contas já vencidas (a receber {fmt_brl(dados['atraso_receber'])}, "
            f"a pagar {fmt_brl(dados['atraso_pagar'])}) entram no início da projeção, "
            "como se fossem liquidadas hoje."
        )
    colunas = {"receber": "A receber", "pagar": "A pagar"}
    _graficos(dados["periodos"], colunas)
    _tabela(dados["periodos"], colunas, agrupamento)


def renderizar(usuario: dict) -> None:
    visao = st.radio("Visão", ["Realizado", "Projetado"], horizontal=True, key="fx_visao")
    if visao == "Realizado":
        _realizado()
    else:
        _projetado()
