"""Módulo Vendas: venda de balcão, baixa de estoque e geração de contas a receber."""
from decimal import Decimal

import pandas as pd
import streamlit as st

from config import DESCONTO_MAX_SEM_APROVACAO, PERFIS_GESTAO
from services import catalogo_service as catalogo
from services import clientes_service as clientes
from services import vendas_service as vendas
from services.auth_service import usuario_atual
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_cpf, fmt_data, fmt_datahora
from utils.ui import avisar_apos_recarregar, exibir_mensagens

usuario = usuario_atual()
pode_ver_custo = usuario["perfil"] in PERFIS_GESTAO

st.title("Vendas")
exibir_mensagens()


def descricao_sku(s: dict) -> str:
    return f"{s['sku']} | {s['produto']} | {s['tamanho']} | {s['cor']}"


def situacao_parcela(parcela: dict) -> str:
    if parcela["status"] == "RECEBIDA":
        return "Recebida"
    if parcela["status"] == "CANCELADA":
        return "Cancelada"
    return "Vencida" if parcela["data_vencimento"] < hoje() else "Aberta"


def nome_cliente(c: dict) -> str:
    return f"{c['nome']} ({fmt_cpf(c['cpf'])})" if c["cpf"] else c["nome"]


abas = st.tabs(["Nova venda", "Histórico"])

# ---------------------------------------------------------------- Nova venda
with abas[0]:
    nonce = st.session_state.get("venda_nonce", 0)
    k = f"venda{nonce}"
    chave_carrinho = f"carrinho_{k}"
    carrinho = st.session_state.setdefault(chave_carrinho, [])

    lista_clientes = clientes.listar_clientes(ativo=True)
    por_cliente = {c["id"]: c for c in lista_clientes}
    c1, c2 = st.columns([1, 3])
    data_venda = c1.date_input(
        "Data da venda", value=hoje(), max_value=hoje(), format="DD/MM/YYYY", key=f"{k}_data"
    )
    cliente_id = c2.selectbox(
        "Cliente (opcional à vista; obrigatório no crédito parcelado)",
        [None] + list(por_cliente),
        format_func=lambda i: "Consumidor final (sem cliente)" if i is None else nome_cliente(por_cliente[i]),
        key=f"{k}_cliente",
    )

    st.markdown("**Itens**")
    no_carrinho = {i["variacao_id"]: i["quantidade"] for i in carrinho}
    disponiveis = {
        s["id"]: s
        for s in catalogo.listar_skus_ativos()
        if s["estoque_atual"] - no_carrinho.get(s["id"], 0) > 0
    }
    if not disponiveis:
        st.warning("Nenhum SKU ativo com estoque disponível para venda.")
    else:
        a, b, c = st.columns([6, 1, 1], vertical_alignment="bottom")
        variacao_id = a.selectbox(
            "SKU",
            list(disponiveis),
            format_func=lambda i: (
                f"{descricao_sku(disponiveis[i])} | {fmt_brl(disponiveis[i]['preco_venda'])} | "
                f"{disponiveis[i]['estoque_atual'] - no_carrinho.get(i, 0)} un."
            ),
            key=f"{k}_sku",
        )
        livre = disponiveis[variacao_id]["estoque_atual"] - no_carrinho.get(variacao_id, 0)
        quantidade = b.number_input(
            "Qtd", min_value=1, max_value=livre, value=1, step=1,
            key=f"{k}_qtd_{variacao_id}_{livre}",
        )
        if c.button("Adicionar", key=f"{k}_adicionar"):
            existente = next((i for i in carrinho if i["variacao_id"] == variacao_id), None)
            if existente:
                existente["quantidade"] += int(quantidade)
            else:
                carrinho.append(
                    {
                        "variacao_id": variacao_id,
                        "quantidade": int(quantidade),
                        "preco_unitario": disponiveis[variacao_id]["preco_venda"],
                        "descricao": descricao_sku(disponiveis[variacao_id]),
                    }
                )
            st.rerun()

    subtotal = Decimal("0.00")
    if carrinho:
        for posicao, item in enumerate(carrinho):
            col_a, col_b, col_c, col_d, col_e = st.columns([5, 1, 2, 2, 1], vertical_alignment="center")
            valor_item = item["quantidade"] * item["preco_unitario"]
            subtotal += valor_item
            col_a.write(item["descricao"])
            col_b.write(f"{item['quantidade']} un.")
            col_c.write(fmt_brl(item["preco_unitario"]))
            col_d.write(fmt_brl(valor_item))
            if col_e.button("", icon=":material/delete:", key=f"{k}_remover_{item['variacao_id']}"):
                carrinho.pop(posicao)
                st.rerun()
    else:
        st.caption("Nenhum item adicionado.")

    st.markdown("**Pagamento**")
    p1, p2, p3 = st.columns([2, 3, 1])
    desconto = p1.number_input(
        "Desconto (R$)", min_value=0.0, value=0.0, step=1.0, format="%.2f", key=f"{k}_desconto"
    )
    forma = p2.selectbox(
        "Forma de pagamento", list(vendas.FORMAS_PAGAMENTO),
        format_func=lambda f: vendas.FORMAS_PAGAMENTO[f], key=f"{k}_forma",
    )
    if not pode_ver_custo and subtotal > 0:
        p1.caption(
            f"Máximo sem aprovação: {fmt_brl(subtotal * DESCONTO_MAX_SEM_APROVACAO)}"
        )
    parcelas = p3.number_input(
        "Parcelas", min_value=1, max_value=12, value=1, step=1,
        disabled=forma != "CREDITO", key=f"{k}_parcelas",
    )
    observacao = st.text_input("Observação (opcional)", key=f"{k}_obs")

    resumo, erro = None, None
    if carrinho:
        try:
            resumo = vendas.calcular_resumo(
                subtotal, desconto, forma, parcelas, usuario["perfil"], cliente_id is not None
            )
        except RegraDeNegocioError as e:
            erro = str(e)

        m1, m2, m3 = st.columns(3)
        m1.metric("Subtotal", fmt_brl(subtotal))
        percentual = (Decimal(str(desconto)) / subtotal * 100) if subtotal else Decimal("0")
        m2.metric(
            "Desconto", fmt_brl(desconto), f"{percentual:.1f}% do subtotal",
            delta_color="off", delta_arrow="off",
        )
        m3.metric("Total", fmt_brl(resumo["total"]) if resumo else "-")

        if erro:
            st.warning(erro)
        elif resumo["num_parcelas"] > 1:
            vencimentos = vendas.calcular_vencimentos(data_venda, resumo["num_parcelas"])
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Parcela": f"{n}/{resumo['num_parcelas']}", "Valor": fmt_brl(v), "Vencimento": fmt_data(d)}
                        for n, (v, d) in enumerate(zip(resumo["parcelas"], vencimentos), start=1)
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        elif forma == "CREDITO":
            st.caption("Crédito à vista: a parcela única vence em 30 dias e fica em contas a receber.")
        else:
            destino = "no caixa da loja" if forma == "DINHEIRO" else "na conta bancária"
            st.caption(f"Recebimento imediato, lançado {destino}.")

    if st.button(
        "Finalizar venda", type="primary", key=f"{k}_finalizar", disabled=not carrinho or erro is not None
    ):
        try:
            resultado = vendas.criar_venda(
                cliente_id=cliente_id,
                data_venda=data_venda,
                desconto=desconto,
                forma_pagamento=forma,
                num_parcelas=parcelas,
                observacao=observacao,
                itens=[
                    {k_: i[k_] for k_ in ("variacao_id", "quantidade", "preco_unitario")}
                    for i in carrinho
                ],
                usuario_id=usuario["id"],
            )
            st.session_state["venda_nonce"] = nonce + 1
            st.session_state.pop(chave_carrinho, None)
            st.session_state["venda_detalhe"] = resultado["id"]
            avisar_apos_recarregar(
                f"Venda #{resultado['id']} registrada: {fmt_brl(resultado['valor_total'])}. "
                "O estoque foi baixado e o financeiro atualizado. Veja o detalhe na aba Histórico."
            )
            st.rerun()
        except RegraDeNegocioError as e:
            st.error(str(e))

# ---------------------------------------------------------------- Histórico
with abas[1]:
    todos_clientes = clientes.listar_clientes()
    nomes_c = {c["id"]: c["nome"] for c in todos_clientes}
    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    filtro_cliente = f1.selectbox(
        "Cliente", [None] + list(nomes_c),
        format_func=lambda i: "Todos" if i is None else nomes_c[i], key="vend_filtro_cliente",
    )
    filtro_forma = f2.selectbox(
        "Forma de pagamento", [None] + list(vendas.FORMAS_PAGAMENTO),
        format_func=lambda f: "Todas" if f is None else vendas.FORMAS_PAGAMENTO[f],
        key="vend_filtro_forma",
    )
    data_de = f3.date_input("Venda a partir de", value=None, format="DD/MM/YYYY", key="vend_de")
    data_ate = f4.date_input("Venda até", value=None, format="DD/MM/YYYY", key="vend_ate")

    limite = 500
    lista = vendas.listar_vendas(filtro_cliente, filtro_forma, data_de, data_ate, limite)
    if not lista:
        st.info("Nenhuma venda encontrada.")
    else:
        faturamento = sum((v["valor_total"] for v in lista), Decimal("0"))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Vendas", len(lista))
        m2.metric("Faturamento", fmt_brl(faturamento))
        m3.metric("Ticket médio", fmt_brl(faturamento / len(lista)))
        m4.metric("Unidades vendidas", sum(v["unidades"] for v in lista))
        if len(lista) == limite:
            st.caption(f"Exibindo as {limite} vendas mais recentes do filtro; os totais consideram apenas elas.")

        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Nº": v["id"],
                        "Data": fmt_datahora(v["data_venda"]),
                        "Cliente": v["cliente"] or "Consumidor final",
                        "Unidades": v["unidades"],
                        "Subtotal": fmt_brl(v["subtotal"]),
                        "Desconto": fmt_brl(v["desconto"]),
                        "Total": fmt_brl(v["valor_total"]),
                        "Pagamento": vendas.rotulo_pagamento(v["forma_pagamento"], v["num_parcelas"]),
                        "Vendedor": v["usuario"],
                    }
                    for v in lista
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        st.subheader("Detalhe da venda")
        por_id = {v["id"]: v for v in lista}
        if st.session_state.get("venda_detalhe") not in por_id:
            st.session_state.pop("venda_detalhe", None)
        venda_id = st.selectbox(
            "Venda",
            list(por_id),
            format_func=lambda i: (
                f"#{i} | {fmt_datahora(por_id[i]['data_venda'])} | "
                f"{por_id[i]['cliente'] or 'Consumidor final'} | {fmt_brl(por_id[i]['valor_total'])}"
            ),
            key="venda_detalhe",
        )
        venda = vendas.buscar_venda(venda_id)

        colunas_resumo = st.columns(4 if pode_ver_custo else 3)
        colunas_resumo[0].metric("Total", fmt_brl(venda["valor_total"]))
        colunas_resumo[1].metric(
            "Pagamento", vendas.rotulo_pagamento(venda["forma_pagamento"], venda["num_parcelas"])
        )
        colunas_resumo[2].metric("Data", fmt_data(venda["data_venda"]))
        if pode_ver_custo:
            custo_total = sum((i["quantidade"] * i["custo_unitario"] for i in venda["itens"]), Decimal("0"))
            margem = venda["valor_total"] - custo_total
            colunas_resumo[3].metric(
                "Margem bruta", fmt_brl(margem), f"{margem / venda['valor_total'] * 100:.1f}%",
                delta_color="off", delta_arrow="off",
            )
        st.caption(
            f"Cliente: {venda['cliente'] or 'Consumidor final'} | Vendedor: {venda['usuario']}"
            + (f" | Desconto: {fmt_brl(venda['desconto'])}" if venda["desconto"] else "")
            + (f" | Observação: {venda['observacao']}" if venda["observacao"] else "")
        )

        linhas_itens = []
        for i in venda["itens"]:
            linha = {
                "SKU": i["sku"],
                "Produto": i["produto"],
                "Tamanho": i["tamanho"],
                "Cor": i["cor"],
                "Quantidade": i["quantidade"],
                "Preço unitário": fmt_brl(i["preco_unitario"]),
            }
            if pode_ver_custo:
                linha["Custo unitário"] = fmt_brl(i["custo_unitario"])
            linha["Subtotal"] = fmt_brl(i["subtotal"])
            linha["Devolvido"] = i["quantidade_devolvida"]
            linhas_itens.append(linha)
        st.dataframe(pd.DataFrame(linhas_itens), hide_index=True, width="stretch")

        if venda["parcelas"]:
            st.markdown("**Contas a receber**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Parcela": f"{p['num_parcela']}/{p['total_parcelas']}",
                            "Valor": fmt_brl(p["valor"]),
                            "Vencimento": fmt_data(p["data_vencimento"]),
                            "Situação": situacao_parcela(p),
                            "Recebida em": fmt_datahora(p["data_recebimento"]),
                            "Conta": p["conta"] or "-",
                        }
                        for p in venda["parcelas"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
