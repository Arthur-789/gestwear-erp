"""Aba Produtos e estoque: ranking, categorias, curva ABC, giro, cobertura e estoque parado."""
from datetime import date

import pandas as pd
import streamlit as st

from services import bi_service as bi
from utils.formatacao import fmt_brl, fmt_brl_md, fmt_data, fmt_decimal, fmt_inteiro, fmt_pct
from views.bi_abas import comum

_METRICAS = {
    "faturamento": ("Faturamento", fmt_brl),
    "unidades": ("Unidades vendidas", fmt_inteiro),
    "margem": ("Margem bruta", fmt_brl),
}


def _produtos(inicio: date, fim: date) -> None:
    ranking = comum.ranking_produtos(inicio, fim)
    if not ranking:
        comum.sem_dados("Nenhum produto vendido no período.")
        return

    metrica = st.radio(
        "Ordenar por", list(_METRICAS), format_func=lambda m: _METRICAS[m][0], horizontal=True, key="bi_prod_metrica"
    )
    nome, formatar = _METRICAS[metrica]
    top = sorted(ranking, key=lambda r: r[metrica], reverse=True)[:10]
    esquerda, direita = st.columns(2)
    with esquerda:
        comum.barras_horizontais([r["produto"] for r in top], [r[metrica] for r in top], nome)
    with direita:
        comum.tabela(
            [
                {
                    "Produto": r["produto"],
                    "Unidades": fmt_inteiro(r["unidades"]),
                    "Faturamento": fmt_brl(r["faturamento"]),
                    "Margem": fmt_brl(r["margem"]),
                    "Margem %": fmt_pct(r["margem_pct"]),
                }
                for r in top
            ]
        )
    st.caption(f"Os 10 produtos com maior {nome.lower()}. O faturamento de cada item já considera o desconto da venda.")

    st.subheader("Categorias")
    categorias = comum.vendas_por_categoria(inicio, fim)
    esquerda, direita = st.columns(2)
    with esquerda:
        st.bar_chart(
            pd.DataFrame(
                {"Faturamento": [float(c["faturamento"]) for c in categorias],
                 "Margem bruta": [float(c["margem"]) for c in categorias]},
                index=[c["categoria"] for c in categorias],
            ),
            stack=False, sort=False, height=320,
        )
    with direita:
        total = sum(c["faturamento"] for c in categorias)
        comum.tabela(
            [
                {
                    "Categoria": c["categoria"],
                    "Unidades": fmt_inteiro(c["unidades"]),
                    "Faturamento": fmt_brl(c["faturamento"]),
                    "Participação": fmt_pct(c["faturamento"] / total),
                    "Margem %": fmt_pct(c["margem_pct"]),
                }
                for c in categorias
            ]
        )

    st.subheader("Curva ABC de produtos")
    abc = bi.curva_abc(ranking)
    classes = {}
    for linha in abc:
        c = classes.setdefault(linha["classe"], {"produtos": 0, "participacao": 0})
        c["produtos"] += 1
        c["participacao"] += linha["participacao"]
    esquerda, direita = st.columns(2)
    with esquerda:
        st.line_chart(
            pd.DataFrame({"Faturamento acumulado (%)": [float(a["acumulado"]) * 100 for a in abc]},
                         index=[a["posicao"] for a in abc]),
            height=260,
        )
        st.caption("Produtos em ordem decrescente de faturamento (eixo horizontal: posição no ranking).")
    with direita:
        comum.tabela(
            [
                {
                    "Classe": classe,
                    "Produtos": fmt_inteiro(classes[classe]["produtos"]),
                    "% dos produtos": fmt_pct(classes[classe]["produtos"] / len(abc)),
                    "% do faturamento": fmt_pct(classes[classe]["participacao"]),
                }
                for classe in sorted(classes)
            ]
        )
        st.caption("A: até 80% do faturamento acumulado; B: até 95%; C: o restante.")
    with st.expander("Ver todos os produtos"):
        comum.tabela(
            [
                {
                    "Posição": a["posicao"],
                    "Produto": a["produto"],
                    "Categoria": a["categoria"],
                    "Unidades": fmt_inteiro(a["unidades"]),
                    "Faturamento": fmt_brl(a["faturamento"]),
                    "Acumulado": fmt_pct(a["acumulado"]),
                    "Classe": a["classe"],
                    "Margem %": fmt_pct(a["margem_pct"]),
                }
                for a in abc
            ]
        )

    st.subheader("Tamanhos e cores mais vendidos")
    tamanhos, cores = comum.vendas_por_tamanho(inicio, fim), comum.vendas_por_cor(inicio, fim)
    esquerda, direita = st.columns(2)
    esquerda.bar_chart(
        pd.DataFrame({"Unidades": [int(t["unidades"]) for t in tamanhos]}, index=[t["tamanho"] for t in tamanhos]),
        sort=False, height=260,
    )
    with direita:
        comum.barras_horizontais([c["cor"] for c in cores], [c["unidades"] for c in cores], "Unidades")


def _estoque(inicio: date, fim: date) -> None:
    posicao = comum.posicao_estoque()
    linhas = comum.giro_por_sku(inicio, fim)
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Valor em estoque (custo)", fmt_brl_md(posicao["valor_custo"]))
    m2.metric("Valor potencial de venda", fmt_brl_md(posicao["valor_venda"]))
    m3.metric("Unidades em estoque", fmt_inteiro(posicao["unidades"]))
    m4.metric("SKUs críticos", fmt_inteiro(posicao["criticos"]), f"de {fmt_inteiro(posicao['skus'])} ativos",
              delta_color="off", delta_arrow="off")
    m5.metric("SKUs zerados", fmt_inteiro(posicao["zerados"]))

    st.subheader("Giro e cobertura por categoria")
    giro = bi.giro_por_categoria(linhas, inicio, fim)
    esquerda, direita = st.columns(2)
    with esquerda:
        com_cobertura = [g for g in giro if g["cobertura_dias"] is not None]
        if com_cobertura:
            comum.barras_horizontais(
                [g["categoria"] for g in com_cobertura], [g["cobertura_dias"] for g in com_cobertura],
                "Cobertura (dias)",
            )
        else:
            comum.sem_dados("Sem vendas no período para calcular a cobertura.")
    with direita:
        comum.tabela(
            [
                {
                    "Categoria": g["categoria"],
                    "Estoque atual": fmt_inteiro(g["estoque_atual"]),
                    "Vendidas": fmt_inteiro(g["vendidas"]),
                    "Giro no período": fmt_decimal(g["giro"], 2),
                    "Cobertura": comum.fmt_dias(g["cobertura_dias"]),
                    "Valor (custo)": fmt_brl(g["valor_custo"]),
                }
                for g in giro
            ]
        )
    st.caption(
        "Giro = unidades vendidas no período ÷ estoque médio (início e fim do período). "
        "Cobertura = quantos dias o estoque no fim do período dura ao ritmo médio de vendas."
    )

    st.subheader("SKUs críticos")
    criticos = bi.skus_criticos(linhas)
    if criticos:
        comum.tabela(
            [
                {
                    "SKU": s["sku"],
                    "Produto": s["produto"],
                    "Tamanho": s["tamanho"],
                    "Cor": s["cor"],
                    "Estoque": s["estoque_atual"],
                    "Mínimo": s["estoque_minimo"],
                    "Vendidas no período": fmt_inteiro(s["vendidas"]),
                    "Cobertura": comum.fmt_dias(s["cobertura_dias"]),
                }
                for s in criticos[:20]
            ]
        )
        if len(criticos) > 20:
            st.caption(f"Exibindo os 20 mais críticos de {len(criticos)}.")
    else:
        st.success("Nenhum SKU no estoque mínimo ou abaixo dele.")

    st.subheader("Estoque parado")
    parados = bi.estoque_parado(linhas)
    valor_parado = sum((s["valor_custo"] for s in parados), 0)
    p1, p2 = st.columns(2)
    p1.metric("SKUs sem venda no período", fmt_inteiro(len(parados)))
    p2.metric("Capital imobilizado (custo)", fmt_brl_md(valor_parado),
              f"{fmt_pct(valor_parado / posicao['valor_custo'])} do estoque" if posicao["valor_custo"] else None,
              delta_color="off", delta_arrow="off")
    if parados:
        comum.tabela(
            [
                {
                    "SKU": s["sku"],
                    "Produto": s["produto"],
                    "Tamanho": s["tamanho"],
                    "Cor": s["cor"],
                    "Estoque": s["estoque_atual"],
                    "Valor (custo)": fmt_brl(s["valor_custo"]),
                    "Última venda": fmt_data(s["ultima_venda"]) if s["ultima_venda"] else "Nunca vendido",
                }
                for s in parados[:20]
            ]
        )
        if len(parados) > 20:
            st.caption(f"Exibindo os 20 de maior valor entre {len(parados)}.")


def renderizar(inicio: date, fim: date, agrupamento: str) -> None:
    st.subheader("Produtos")
    _produtos(inicio, fim)
    st.divider()
    st.header("Estoque")
    _estoque(inicio, fim)
