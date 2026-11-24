"""Aba Vendas: formas de pagamento, vendedores, dias da semana, descontos e clientes."""
from datetime import date

import pandas as pd
import streamlit as st

from services import vendas_service
from utils.formatacao import fmt_brl, fmt_data, fmt_inteiro, fmt_pct
from views.bi_abas import comum


def renderizar(inicio: date, fim: date, agrupamento: str) -> None:
    resumo = comum.indicadores(inicio, fim)
    if not resumo["num_vendas"]:
        comum.sem_dados()
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Vendas", fmt_inteiro(resumo["num_vendas"]))
    m2.metric("Descontos concedidos", fmt_brl(resumo["descontos"]),
              f"{fmt_pct(resumo['desconto_medio_pct'])} do valor bruto", delta_color="off", delta_arrow="off")
    m3.metric("Vendas com cliente identificado", fmt_pct(resumo["vendas_com_cliente"] / resumo["num_vendas"]),
              f"{fmt_inteiro(resumo['clientes_ativos'])} clientes", delta_color="off", delta_arrow="off")
    m4.metric("Unidades vendidas", fmt_inteiro(resumo["unidades"]))

    st.subheader("Formas de pagamento")
    formas = comum.vendas_por_forma_pagamento(inicio, fim)
    total = sum(f["faturamento"] for f in formas)
    esquerda, direita = st.columns(2)
    with esquerda:
        comum.barras_horizontais(
            [vendas_service.FORMAS_PAGAMENTO[f["forma_pagamento"]] for f in formas],
            [f["faturamento"] for f in formas], "Faturamento (R$)",
        )
    with direita:
        comum.tabela(
            [
                {
                    "Forma": vendas_service.FORMAS_PAGAMENTO[f["forma_pagamento"]],
                    "Vendas": fmt_inteiro(f["num_vendas"]),
                    "Faturamento": fmt_brl(f["faturamento"]),
                    "Participação": fmt_pct(f["faturamento"] / total),
                    "Ticket médio": fmt_brl(f["ticket_medio"]),
                }
                for f in formas
            ]
        )

    parcelas = comum.vendas_por_parcelas(inicio, fim)
    if parcelas:
        st.markdown("**Crédito: vendas por número de parcelas**")
        st.bar_chart(
            pd.DataFrame(
                {"Faturamento (R$)": [float(p["faturamento"]) for p in parcelas]},
                index=[f"{p['num_parcelas']}x" for p in parcelas],
            ),
            sort=False, height=240,
        )

    st.subheader("Dias da semana")
    dias = comum.vendas_por_dia_semana(inicio, fim)
    esquerda, direita = st.columns(2)
    with esquerda:
        st.bar_chart(
            pd.DataFrame({"Faturamento médio por dia (R$)": [float(d["media_por_dia"]) for d in dias]},
                         index=[d["nome"] for d in dias]),
            sort=False, height=280,
        )
    with direita:
        comum.tabela(
            [
                {"Dia": d["nome"], "Vendas": fmt_inteiro(d["num_vendas"]), "Faturamento": fmt_brl(d["faturamento"]),
                 "Média por dia": fmt_brl(d["media_por_dia"])}
                for d in dias
            ]
        )

    st.subheader("Vendedores")
    vendedores = comum.vendas_por_vendedor(inicio, fim)
    esquerda, direita = st.columns(2)
    with esquerda:
        comum.barras_horizontais(
            [v["vendedor"] for v in vendedores], [v["faturamento"] for v in vendedores], "Faturamento (R$)"
        )
    with direita:
        comum.tabela(
            [
                {
                    "Vendedor": v["vendedor"],
                    "Vendas": fmt_inteiro(v["num_vendas"]),
                    "Faturamento": fmt_brl(v["faturamento"]),
                    "Ticket médio": fmt_brl(v["ticket_medio"]),
                    "Desconto médio": fmt_pct(v["desconto_pct"]),
                }
                for v in vendedores
            ]
        )
    st.caption("Descontos acima de 10% só podem ser concedidos por Gerente ou Administrador.")

    st.subheader("Descontos")
    faixas = comum.faixas_desconto(inicio, fim)
    comum.tabela(
        [
            {
                "Faixa": f["faixa"][3:],
                "Vendas": fmt_inteiro(f["num_vendas"]),
                "% das vendas": fmt_pct(f["num_vendas"] / resumo["num_vendas"]),
                "Faturamento": fmt_brl(f["faturamento"]),
                "Desconto total": fmt_brl(f["descontos"]),
            }
            for f in faixas
        ]
    )

    st.subheader("Melhores clientes")
    clientes = comum.top_clientes(inicio, fim, 10)
    if clientes:
        comum.tabela(
            [
                {
                    "Cliente": c["cliente"],
                    "Compras": fmt_inteiro(c["compras"]),
                    "Faturamento": fmt_brl(c["faturamento"]),
                    "Ticket médio": fmt_brl(c["ticket_medio"]),
                    "Última compra": fmt_data(c["ultima_compra"]),
                }
                for c in clientes
            ]
        )
    else:
        comum.sem_dados("Nenhuma venda com cliente identificado no período.")
