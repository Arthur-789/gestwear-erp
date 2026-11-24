"""Aba Visão geral: indicadores principais, evolução, resultado e destaques do período."""
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import bi_service as bi
from services import vendas_service
from utils.formatacao import fmt_brl, fmt_decimal, fmt_inteiro, fmt_pct
from views.bi_abas import comum


def _destaques(atual: dict, anterior: dict, inicio: date, fim: date) -> list[str]:
    """Leituras automáticas dos dados do período (nada é fixo: tudo vem das consultas)."""
    textos = []
    variacao = bi.variacao(atual["faturamento"], anterior["faturamento"])
    if variacao is not None:
        sentido = "alta" if variacao >= 0 else "queda"
        textos.append(
            f"O faturamento foi de {fmt_brl(atual['faturamento'])}, com {sentido} de "
            f"{fmt_pct(abs(variacao))} sobre o período anterior ({fmt_brl(anterior['faturamento'])})."
        )
    elif atual["num_vendas"]:
        textos.append(f"O faturamento foi de {fmt_brl(atual['faturamento'])} (sem período anterior para comparar).")
    if atual["margem_pct"] is not None:
        textos.append(
            f"A margem bruta foi de {fmt_pct(atual['margem_pct'])}"
            + (
                f", contra {fmt_pct(anterior['margem_pct'])} no período anterior."
                if anterior["margem_pct"] is not None else "."
            )
        )
    dias = comum.vendas_por_dia_semana(inicio, fim)
    if atual["num_vendas"] and (fim - inicio).days >= 13:
        melhor = max(dias, key=lambda d: d["media_por_dia"])
        pior = min(dias, key=lambda d: d["media_por_dia"])
        textos.append(
            f"{melhor['nome']} é o dia mais forte (média de {fmt_brl(melhor['media_por_dia'])} por dia) "
            f"e {pior['nome'].lower()} o mais fraco ({fmt_brl(pior['media_por_dia'])})."
        )
    formas = comum.vendas_por_forma_pagamento(inicio, fim)
    if formas and atual["faturamento"]:
        lider = formas[0]
        textos.append(
            f"{vendas_service.FORMAS_PAGAMENTO[lider['forma_pagamento']]} é a forma de pagamento predominante, "
            f"com {fmt_pct(lider['faturamento'] / atual['faturamento'])} do faturamento."
        )
    categorias = comum.vendas_por_categoria(inicio, fim)
    if categorias and atual["faturamento"]:
        total = sum(c["faturamento"] for c in categorias)
        textos.append(
            f"A categoria {categorias[0]['categoria']} lidera as vendas, com {fmt_pct(categorias[0]['faturamento'] / total)} "
            f"do faturamento."
        )
    contas = comum.situacao_contas()
    if contas["receber"]["vencido"]:
        textos.append(
            f"Há {fmt_brl(contas['receber']['vencido'])} vencidos a receber, "
            f"{fmt_pct(contas['receber']['pct_vencido'])} da carteira em aberto."
        )
    estoque = comum.posicao_estoque()
    if estoque["criticos"]:
        textos.append(f"{fmt_inteiro(estoque['criticos'])} SKU(s) estão no estoque mínimo ou abaixo dele.")
    return textos


def _demonstracao(atual: dict, anterior: dict) -> None:
    linhas = [
        ("Faturamento (vendas)", "faturamento"),
        ("(-) Devoluções e trocas: valor devolvido", "valor_devolvido"),
        ("(+) Trocas: valor dos itens novos", "valor_novos"),
        ("= Receita líquida", "receita_liquida"),
        ("(-) Custo das mercadorias (CMV)", "cmv"),
        ("= Margem bruta", "margem_bruta"),
        ("(-) Despesas operacionais", "despesas"),
        ("= Resultado do período", "resultado"),
    ]
    registros = []
    for rotulo, chave in linhas:
        variacao = bi.variacao(atual[chave], anterior[chave])
        registros.append(
            {
                "Linha": rotulo,
                "Período": fmt_brl(atual[chave]),
                "Período anterior": fmt_brl(anterior[chave]),
                "Variação": fmt_pct(variacao, 1, sinal=True) if variacao is not None else "-",
            }
        )
    registros.insert(6, {"Linha": "Margem bruta (%)", "Período": fmt_pct(atual["margem_pct"]),
                         "Período anterior": fmt_pct(anterior["margem_pct"]), "Variação": "-"})
    comum.tabela(registros)
    st.caption(
        "Receita líquida = vendas - valor devolvido + itens novos das trocas. CMV considera o custo gravado em cada "
        "venda, desconta o que voltou ao estoque e inclui o custo dos itens de troca. Itens devolvidos por defeito "
        "permanecem no CMV (perda). Despesas operacionais são as despesas avulsas pelo vencimento no período."
    )


def renderizar(inicio: date, fim: date, agrupamento: str) -> None:
    atual = comum.indicadores(inicio, fim)
    inicio_anterior, fim_anterior = bi.periodo_anterior(inicio, fim)
    anterior = comum.indicadores(inicio_anterior, fim_anterior)
    tem_base = anterior["num_vendas"] > 0

    def delta(chave: str) -> str | None:
        return comum.pct_variacao(atual[chave], anterior[chave]) if tem_base else None

    if not atual["num_vendas"]:
        comum.sem_dados("Não há vendas no período selecionado. Os indicadores abaixo ficam zerados.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Faturamento", fmt_brl(atual["faturamento"]), delta("faturamento"), help="Soma das vendas, já com desconto.")
    m2.metric("Receita líquida", fmt_brl(atual["receita_liquida"]), delta("receita_liquida"),
              help="Vendas menos devoluções, mais os itens novos das trocas.")
    m3.metric("Margem bruta", fmt_brl(atual["margem_bruta"]), delta("margem_bruta"),
              help=f"Receita líquida menos o custo das mercadorias ({fmt_pct(atual['margem_pct'])} da receita).")
    m4.metric("Resultado", fmt_brl(atual["resultado"]),
              comum.pct_variacao(atual["resultado"], anterior["resultado"]) if tem_base and anterior["resultado"] > 0 else None,
              help="Margem bruta menos as despesas operacionais do período.")

    m5, m6, m7, m8 = st.columns(4)
    m5.metric("Vendas", fmt_inteiro(atual["num_vendas"]), delta("num_vendas"))
    m6.metric("Ticket médio", fmt_brl(atual["ticket_medio"]), delta("ticket_medio"))
    m7.metric("Itens por venda", fmt_decimal(atual["itens_por_venda"], 2), delta("itens_por_venda"))
    m8.metric("Margem bruta (%)", fmt_pct(atual["margem_pct"]),
              None if atual["margem_pct"] is None or anterior["margem_pct"] is None
              else f"{(atual['margem_pct'] - anterior['margem_pct']) * 100:+.1f} p.p.".replace(".", ","))

    st.markdown("**Situação atual** (independe do período)")
    contas = comum.situacao_contas()
    estoque = comum.posicao_estoque()
    saldo = sum((c["saldo_atual"] for c in comum.contas_financeiras(True)), Decimal("0.00"))
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Saldo em caixa e bancos", fmt_brl(saldo))
    s2.metric("A receber vencido", fmt_brl(contas["receber"]["vencido"]),
              f"{fmt_pct(contas['receber']['pct_vencido'])} da carteira", delta_color="off", delta_arrow="off")
    s3.metric("A pagar vencido", fmt_brl(contas["pagar"]["vencido"]))
    s4.metric("SKUs em estoque crítico", fmt_inteiro(estoque["criticos"]),
              f"{fmt_inteiro(estoque['zerados'])} zerados", delta_color="off", delta_arrow="off")

    st.subheader("Evolução no período")
    pontos = comum.serie(inicio, fim, agrupamento)
    indice = pd.to_datetime([p["periodo"] for p in pontos])
    st.line_chart(
        pd.DataFrame(
            {
                "Faturamento": [float(p["faturamento"]) for p in pontos],
                "Margem bruta": [float(p["margem_bruta"]) for p in pontos],
            },
            index=indice,
        ),
        height=320,
    )
    g1, g2 = st.columns(2)
    g1.markdown("**Número de vendas**")
    g1.bar_chart(pd.DataFrame({"Vendas": [p["num_vendas"] for p in pontos]}, index=indice), height=240)
    g2.markdown("**Ticket médio (R$)**")
    g2.line_chart(pd.DataFrame({"Ticket médio": [float(p["ticket_medio"]) for p in pontos]}, index=indice), height=240)

    st.subheader("Demonstração do resultado")
    _demonstracao(atual, anterior)

    st.subheader("Destaques")
    destaques = _destaques(atual, anterior, inicio, fim)
    if destaques:
        for texto in destaques:
            st.markdown(f"- {texto}")
    else:
        comum.sem_dados()
