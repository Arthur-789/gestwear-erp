"""Aba Operações: trocas e devoluções, perdas e compras por fornecedor."""
from datetime import date

import pandas as pd
import streamlit as st

from services import operacional_service
from utils.formatacao import fmt_brl, fmt_decimal, fmt_inteiro, fmt_pct
from views.bi_abas import comum


def _trocas_devolucoes(inicio: date, fim: date, resumo: dict) -> None:
    total = resumo["devolucoes"] + resumo["trocas"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trocas e devoluções", fmt_inteiro(total), f"{fmt_inteiro(resumo['devolucoes'])} devoluções e "
              f"{fmt_inteiro(resumo['trocas'])} trocas", delta_color="off", delta_arrow="off")
    m2.metric("Valor devolvido", fmt_brl(resumo["valor_devolvido"]),
              f"{fmt_pct(resumo['taxa_devolucao_valor'])} do faturamento", delta_color="off", delta_arrow="off")
    m3.metric("Unidades devolvidas", fmt_inteiro(resumo["unidades_devolvidas"]),
              f"{fmt_pct(resumo['taxa_devolucao_unidades'])} das vendidas", delta_color="off", delta_arrow="off")
    m4.metric("Perda por defeito (custo)", fmt_brl(resumo["perda_defeito"]))
    if not total:
        comum.sem_dados("Nenhuma troca ou devolução no período.")
        return

    st.markdown("**Por motivo**")
    motivos = comum.devolucoes_por_motivo(inicio, fim)
    esquerda, direita = st.columns(2)
    with esquerda:
        st.bar_chart(
            pd.DataFrame(
                {"Devoluções": [m["devolucoes"] for m in motivos], "Trocas": [m["trocas"] for m in motivos]},
                index=[operacional_service.MOTIVOS[m["motivo"]] for m in motivos],
            ),
            stack=True, sort=False, height=280,
        )
    with direita:
        comum.tabela(
            [
                {
                    "Motivo": operacional_service.MOTIVOS[m["motivo"]],
                    "Solicitações": fmt_inteiro(m["total"]),
                    "% do total": fmt_pct(m["total"] / total),
                    "Unidades": fmt_inteiro(m["unidades"]),
                    "Valor devolvido": fmt_brl(m["valor_devolvido"]),
                }
                for m in motivos
            ]
        )

    st.markdown("**Produtos mais devolvidos**")
    produtos = comum.produtos_mais_devolvidos(inicio, fim, 10)
    comum.tabela(
        [
            {
                "Produto": p["produto"],
                "Devolvidas": fmt_inteiro(p["devolvidas"]),
                "Vendidas": fmt_inteiro(p["vendidas"]),
                "Índice de devolução": fmt_pct(p["indice"]),
                "Por defeito": fmt_inteiro(p["por_defeito"]),
            }
            for p in produtos
        ]
    )
    st.caption("Índice = unidades devolvidas ÷ unidades vendidas no mesmo período (as devoluções podem vir de vendas anteriores).")


def _compras(inicio: date, fim: date, agrupamento: str) -> None:
    fornecedores = comum.compras_por_fornecedor(inicio, fim)
    if not fornecedores:
        comum.sem_dados("Nenhuma compra no período.")
        return
    valor_total = sum(f["valor"] for f in fornecedores)
    pedidos = sum(f["pedidos"] for f in fornecedores)
    pendentes = sum(f["pendentes"] for f in fornecedores)
    m1, m2, m3 = st.columns(3)
    m1.metric("Compras no período", fmt_brl(valor_total), f"{fmt_inteiro(pedidos)} pedidos", delta_color="off", delta_arrow="off")
    m2.metric("Pedidos aguardando recebimento", fmt_inteiro(pendentes))
    prazos = [f["prazo_medio_dias"] for f in fornecedores if f["prazo_medio_dias"] is not None]
    m3.metric("Prazo médio de entrega", comum.fmt_dias(sum(prazos) / len(prazos)) if prazos else "-")

    esquerda, direita = st.columns(2)
    with esquerda:
        comum.barras_horizontais([f["fornecedor"] for f in fornecedores], [f["valor"] for f in fornecedores],
                                 "Compras (R$)")
    with direita:
        comum.tabela(
            [
                {
                    "Fornecedor": f["fornecedor"],
                    "Pedidos": fmt_inteiro(f["pedidos"]),
                    "Unidades": fmt_inteiro(f["unidades"]),
                    "Valor": fmt_brl(f["valor"]),
                    "Participação": fmt_pct(f["valor"] / valor_total),
                    "Prazo médio": fmt_decimal(f["prazo_medio_dias"], 1) + " dias" if f["prazo_medio_dias"] is not None else "-",
                }
                for f in fornecedores
            ]
        )

    st.markdown("**Compras x custo das mercadorias vendidas**")
    compras = comum.compras_serie(inicio, fim, agrupamento)
    vendas = comum.serie(inicio, fim, agrupamento)
    st.line_chart(
        pd.DataFrame(
            {"Compras": [float(c["compras"]) for c in compras], "CMV": [float(v["cmv"]) for v in vendas]},
            index=pd.to_datetime([c["periodo"] for c in compras]),
        ),
        height=280,
    )
    st.caption("Compras acima do CMV indicam formação de estoque; abaixo, consumo do estoque existente.")


def renderizar(inicio: date, fim: date, agrupamento: str) -> None:
    resumo = comum.indicadores(inicio, fim)
    st.subheader("Trocas e devoluções")
    _trocas_devolucoes(inicio, fim, resumo)
    st.subheader("Compras e fornecedores")
    _compras(inicio, fim, agrupamento)
