"""Aba Financeiro: caixa, resultado, despesas, inadimplência e projeção."""
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import tesouraria_service as tesouraria
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_inteiro, fmt_pct
from views.bi_abas import comum

_VERDE, _VERMELHO = "#2e7d32", "#c62828"


def _contas() -> None:
    contas = comum.contas_financeiras(True)
    total = sum((c["saldo_atual"] for c in contas), Decimal("0.00"))
    colunas = st.columns(len(contas) + 1)
    colunas[0].metric("Saldo total", fmt_brl(total))
    for coluna, conta in zip(colunas[1:], contas):
        coluna.metric(f"{conta['nome']} ({tesouraria.TIPOS_CONTA[conta['tipo']]})", fmt_brl(conta["saldo_atual"]))

    situacao = comum.situacao_contas()
    r, p = situacao["receber"], situacao["pagar"]
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("A receber em aberto", fmt_brl(r["aberto"]))
    a2.metric("A receber vencido", fmt_brl(r["vencido"]),
              f"{fmt_pct(r['pct_vencido'])} da carteira", delta_color="off", delta_arrow="off")
    a3.metric("A receber (30 dias)", fmt_brl(r["a_vencer_30"]), f"{fmt_brl(r['a_vencer_7'])} em 7 dias",
              delta_color="off", delta_arrow="off")
    a4.metric("Parcelas vencidas a receber", fmt_inteiro(r["qtd_vencidas"]))
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("A pagar em aberto", fmt_brl(p["aberto"]))
    b2.metric("A pagar vencido", fmt_brl(p["vencido"]))
    b3.metric("A pagar (30 dias)", fmt_brl(p["a_vencer_30"]), f"{fmt_brl(p['a_vencer_7'])} em 7 dias",
              delta_color="off", delta_arrow="off")
    b4.metric("Contas vencidas a pagar", fmt_inteiro(p["qtd_vencidas"]))


def _fluxo_realizado(inicio: date, fim: date, agrupamento: str) -> None:
    # O fluxo de caixa trabalha por dia ou por mês
    por = "month" if agrupamento == "month" or (fim - inicio).days > 366 else "day"
    dados = comum.fluxo_realizado(inicio, fim, por, None)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo no início", fmt_brl(dados["saldo_inicial"]))
    m2.metric("Entradas", fmt_brl(dados["total_entradas"]))
    m3.metric("Saídas", fmt_brl(dados["total_saidas"]))
    m4.metric("Saldo no fim", fmt_brl(dados["saldo_final"]))
    pontos = dados["periodos"]
    indice = pd.to_datetime([p["periodo"] for p in pontos])
    esquerda, direita = st.columns(2)
    esquerda.markdown("**Entradas e saídas**")
    esquerda.bar_chart(
        pd.DataFrame({"Entradas": [float(p["entradas"]) for p in pontos],
                      "Saídas": [float(p["saidas"]) for p in pontos]}, index=indice),
        color=[_VERDE, _VERMELHO], stack=False, height=280,
    )
    direita.markdown("**Saldo acumulado**")
    direita.line_chart(
        pd.DataFrame({"Saldo": [float(p["saldo_acumulado"]) for p in pontos]}, index=indice), height=280
    )


def _resultado(inicio: date, fim: date, agrupamento: str) -> None:
    pontos = comum.serie(inicio, fim, agrupamento)
    indice = pd.to_datetime([p["periodo"] for p in pontos])
    st.line_chart(
        pd.DataFrame(
            {
                "Margem bruta": [float(p["margem_bruta"]) for p in pontos],
                "Despesas": [float(p["despesas"]) for p in pontos],
                "Resultado": [float(p["resultado"]) for p in pontos],
            },
            index=indice,
        ),
        height=300,
    )
    st.caption(
        "Visão por competência aproximada: a margem considera a data das vendas e trocas; as despesas, o vencimento. "
        "Em períodos curtos, despesas mensais podem cair inteiras em um único ponto."
    )


def _despesas(inicio: date, fim: date) -> None:
    despesas = comum.despesas_por_categoria(inicio, fim)
    if not despesas:
        comum.sem_dados("Nenhuma despesa avulsa com vencimento no período.")
        return
    esquerda, direita = st.columns(2)
    with esquerda:
        comum.barras_horizontais([d["categoria"] for d in despesas], [d["valor"] for d in despesas], "Despesas (R$)")
    with direita:
        total = sum(d["valor"] for d in despesas)
        comum.tabela(
            [
                {
                    "Categoria": d["categoria"],
                    "Valor": fmt_brl(d["valor"]),
                    "Participação": fmt_pct(d["valor"] / total),
                    "Pago": fmt_brl(d["pago"]),
                    "Pendente": fmt_brl(d["pendente"]),
                }
                for d in despesas
            ]
        )


def _inadimplencia() -> None:
    receber = comum.situacao_contas()["receber"]
    if not receber["faixas"]:
        st.success("Não há parcelas vencidas a receber.")
        return
    esquerda, direita = st.columns(2)
    with esquerda:
        st.markdown("**Parcelas vencidas por tempo de atraso**")
        st.bar_chart(
            pd.DataFrame({"Valor (R$)": [float(f["valor"]) for f in receber["faixas"]]},
                         index=[f["faixa"] for f in receber["faixas"]]),
            sort=False, height=260,
        )
    with direita:
        st.markdown("**Clientes com maior valor em atraso**")
        comum.tabela(
            [
                {
                    "Cliente": c["cliente"],
                    "Parcelas": fmt_inteiro(c["parcelas"]),
                    "Valor": fmt_brl(c["valor"]),
                    "Maior atraso": comum.fmt_dias(c["maior_atraso"]),
                }
                for c in comum.clientes_em_atraso(8)
            ]
        )


def _projecao() -> None:
    dados = comum.fluxo_projetado(hoje() + timedelta(days=30), "day")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo atual", fmt_brl(dados["saldo_inicial"]))
    m2.metric("A receber (inclui vencidas)", fmt_brl(dados["total_receber"]))
    m3.metric("A pagar (inclui vencidas)", fmt_brl(dados["total_pagar"]))
    m4.metric("Saldo projetado em 30 dias", fmt_brl(dados["saldo_final"]))
    pontos = dados["periodos"]
    st.line_chart(
        pd.DataFrame({"Saldo projetado": [float(p["saldo_acumulado"]) for p in pontos]},
                     index=pd.to_datetime([p["periodo"] for p in pontos])),
        height=260,
    )
    st.caption("Projeção a partir do saldo atual e das contas em aberto por vencimento; as já vencidas entram no primeiro dia.")


def renderizar(inicio: date, fim: date, agrupamento: str) -> None:
    st.subheader("Posição financeira atual")
    _contas()
    st.subheader("Fluxo de caixa realizado no período")
    _fluxo_realizado(inicio, fim, agrupamento)
    st.subheader("Margem, despesas e resultado")
    _resultado(inicio, fim, agrupamento)
    st.subheader("Despesas por categoria")
    _despesas(inicio, fim)
    st.subheader("Inadimplência")
    _inadimplencia()
    st.subheader("Projeção de caixa para os próximos 30 dias")
    _projecao()
