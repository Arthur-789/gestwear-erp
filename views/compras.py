"""Módulo Compras: pedidos, recebimento e geração de contas a pagar."""
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import catalogo_service as catalogo
from services import compras_service as compras
from services import fornecedores_service as fornecedores
from services.auth_service import exigir_perfil
from services.excecoes import RegraDeNegocioError
from utils.datas import data_local, hoje
from utils.formatacao import fmt_brl, fmt_data
from utils.ui import avisar_apos_recarregar, exibir_mensagens

usuario = exigir_perfil("ADMIN", "GERENTE")

st.title("Compras")
exibir_mensagens()


def descricao_sku(s: dict) -> str:
    return f"{s['sku']} | {s['produto']} | {s['tamanho']} | {s['cor']}"


def subtotal(item: dict) -> Decimal:
    return Decimal(str(item["quantidade"])) * Decimal(str(item["custo_unitario"]))


def editor_pedido(chave: str, inicial: dict, rotulo_botao: str) -> dict | None:
    """Formulário do pedido com lista de itens mantida na sessão.

    Devolve os dados quando o botão de salvar é acionado; senão, None.
    """
    chave_carrinho = f"carrinho_{chave}"
    if chave_carrinho not in st.session_state:
        st.session_state[chave_carrinho] = [dict(i) for i in inicial["itens"]]
    carrinho = st.session_state[chave_carrinho]

    lista_fornecedores = [
        f
        for f in fornecedores.listar_fornecedores()
        if f["ativo"] or f["id"] == inicial["fornecedor_id"]
    ]
    if not lista_fornecedores:
        st.warning("Cadastre um fornecedor antes de criar pedidos.")
        return None
    nomes = {f["id"]: f["razao_social"] for f in lista_fornecedores}
    ids = list(nomes)
    indice = ids.index(inicial["fornecedor_id"]) if inicial["fornecedor_id"] in ids else 0

    c1, c2 = st.columns([3, 1])
    fornecedor_id = c1.selectbox(
        "Fornecedor", ids, index=indice, format_func=lambda i: nomes[i], key=f"{chave}_fornecedor"
    )
    data_pedido = c2.date_input(
        "Data do pedido", value=inicial["data_pedido"], max_value=hoje(),
        format="DD/MM/YYYY", key=f"{chave}_data",
    )
    c3, c4, c5 = st.columns([1, 1, 3])
    num_parcelas = c3.number_input(
        "Parcelas", min_value=1, max_value=compras.MAX_PARCELAS,
        value=inicial["num_parcelas"], step=1, key=f"{chave}_parcelas",
    )
    primeiro_vencimento = c4.date_input(
        "1º vencimento", value=inicial["primeiro_vencimento"],
        format="DD/MM/YYYY", key=f"{chave}_vencimento",
    )
    observacao = c5.text_input("Observação (opcional)", value=inicial["observacao"], key=f"{chave}_obs")

    st.markdown("**Itens do pedido**")
    skus = catalogo.listar_skus_ativos()
    if not skus:
        st.warning("Cadastre produtos e variações para montar o pedido.")
    else:
        por_id = {s["id"]: s for s in skus}
        a, b, c, d = st.columns([5, 1, 2, 1], vertical_alignment="bottom")
        variacao_id = a.selectbox(
            "SKU", list(por_id), format_func=lambda i: descricao_sku(por_id[i]), key=f"{chave}_sku"
        )
        quantidade = b.number_input("Qtd", min_value=1, value=1, step=1, key=f"{chave}_qtd")
        custo = c.number_input(
            "Custo unitário (R$)", min_value=0.0, value=float(por_id[variacao_id]["custo_medio"]),
            step=1.0, format="%.2f", key=f"{chave}_custo_{variacao_id}",
        )
        if d.button("Adicionar", key=f"{chave}_adicionar"):
            novo = {
                "variacao_id": variacao_id,
                "quantidade": int(quantidade),
                "custo_unitario": float(custo),
                "descricao": descricao_sku(por_id[variacao_id]),
            }
            existente = next((i for i in carrinho if i["variacao_id"] == variacao_id), None)
            if existente:
                existente.update(novo)
            else:
                carrinho.append(novo)

    if carrinho:
        for posicao, item in enumerate(carrinho):
            col_a, col_b, col_c, col_d, col_e = st.columns([5, 1, 2, 2, 1], vertical_alignment="center")
            col_a.write(item["descricao"])
            col_b.write(item["quantidade"])
            col_c.write(fmt_brl(item["custo_unitario"]))
            col_d.write(fmt_brl(subtotal(item)))
            if col_e.button("", icon=":material/delete:", key=f"{chave}_remover_{item['variacao_id']}"):
                carrinho.pop(posicao)
                st.rerun()
        total = sum((subtotal(i) for i in carrinho), Decimal("0"))
        st.markdown(f"**Total do pedido: {fmt_brl(total)}**")
    else:
        st.caption("Nenhum item adicionado.")

    if st.button(rotulo_botao, type="primary", key=f"{chave}_salvar"):
        return {
            "fornecedor_id": fornecedor_id,
            "data_pedido": data_pedido,
            "num_parcelas": num_parcelas,
            "primeiro_vencimento": primeiro_vencimento,
            "observacao": observacao,
            "itens": [
                {k: i[k] for k in ("variacao_id", "quantidade", "custo_unitario")} for i in carrinho
            ],
        }
    return None


abas = st.tabs(["Lista", "Novo pedido", "Gerenciar pedido"])

# ---------------------------------------------------------------- Lista
with abas[0]:
    todos_fornecedores = fornecedores.listar_fornecedores()
    nomes_f = {f["id"]: f["razao_social"] for f in todos_fornecedores}
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    filtro_fornecedor = c1.selectbox(
        "Fornecedor", [None] + list(nomes_f),
        format_func=lambda i: "Todos" if i is None else nomes_f[i], key="comp_filtro_forn",
    )
    filtro_status = c2.selectbox(
        "Situação", [None] + list(compras.STATUS_COMPRA),
        format_func=lambda s: "Todas" if s is None else compras.STATUS_COMPRA[s], key="comp_filtro_status",
    )
    data_de = c3.date_input("Pedido a partir de", value=None, format="DD/MM/YYYY", key="comp_de")
    data_ate = c4.date_input("Pedido até", value=None, format="DD/MM/YYYY", key="comp_ate")
    lista = compras.listar_compras(filtro_fornecedor, filtro_status, data_de, data_ate)
    if not lista:
        st.info("Nenhum pedido encontrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Nº": c["id"],
                        "Fornecedor": c["fornecedor"],
                        "Pedido": fmt_data(c["data_pedido"]),
                        "Recebimento": fmt_data(c["data_recebimento"]),
                        "Itens": c["itens"],
                        "Valor": fmt_brl(c["valor_total"]),
                        "Parcelas": c["num_parcelas"],
                        "Situação": compras.STATUS_COMPRA[c["status"]],
                        "Responsável": c["usuario"],
                    }
                    for c in lista
                ]
            ),
            hide_index=True,
            width="stretch",
        )

# ---------------------------------------------------------------- Novo pedido
with abas[1]:
    nonce = st.session_state.get("pedido_nonce", 0)
    chave_novo = f"novo{nonce}"
    dados = editor_pedido(
        chave_novo,
        {
            "fornecedor_id": None,
            "data_pedido": hoje(),
            "num_parcelas": 1,
            "primeiro_vencimento": hoje() + timedelta(days=30),
            "observacao": "",
            "itens": [],
        },
        "Salvar pedido",
    )
    if dados:
        try:
            novo_id = compras.criar_pedido(**dados, usuario_id=usuario["id"])
            st.session_state["pedido_nonce"] = nonce + 1
            st.session_state.pop(f"carrinho_{chave_novo}", None)
            st.session_state["compra_gerenciar"] = novo_id
            avisar_apos_recarregar(
                f"Pedido #{novo_id} salvo. Na aba Gerenciar pedido, registre o recebimento quando a mercadoria chegar."
            )
            st.rerun()
        except RegraDeNegocioError as e:
            st.error(str(e))

# ---------------------------------------------------------------- Gerenciar
with abas[2]:
    todas = compras.listar_compras()
    if not todas:
        st.info("Nenhum pedido cadastrado.")
        st.stop()

    por_id = {c["id"]: c for c in todas}
    compra_id = st.selectbox(
        "Pedido de compra",
        list(por_id),
        format_func=lambda i: (
            f"#{i} | {por_id[i]['fornecedor']} | {fmt_data(por_id[i]['data_pedido'])} | "
            f"{fmt_brl(por_id[i]['valor_total'])} | {compras.STATUS_COMPRA[por_id[i]['status']]}"
        ),
        key="compra_gerenciar",
    )
    compra = compras.buscar_compra(compra_id)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Situação", compras.STATUS_COMPRA[compra["status"]])
    m2.metric("Valor total", fmt_brl(compra["valor_total"]))
    m3.metric("Pedido em", fmt_data(compra["data_pedido"]))
    m4.metric("Recebimento", fmt_data(compra["data_recebimento"]))
    st.caption(
        f"Fornecedor: {compra['fornecedor']} | Responsável: {compra['usuario']}"
        + (f" | Observação: {compra['observacao']}" if compra["observacao"] else "")
    )

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "SKU": i["sku"],
                    "Produto": i["produto"],
                    "Tamanho": i["tamanho"],
                    "Cor": i["cor"],
                    "Quantidade": i["quantidade"],
                    "Custo unitário": fmt_brl(i["custo_unitario"]),
                    "Subtotal": fmt_brl(i["subtotal"]),
                }
                for i in compra["itens"]
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    if compra["parcelas"]:
        st.markdown("**Contas a pagar geradas**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Parcela": f"{p['num_parcela']}/{p['total_parcelas']}",
                        "Valor": fmt_brl(p["valor"]),
                        "Vencimento": fmt_data(p["data_vencimento"]),
                        "Situação": p["status"].title(),
                    }
                    for p in compra["parcelas"]
                ]
            ),
            hide_index=True,
            width="stretch",
        )

    if compra["status"] == "PEDIDO":
        st.subheader("Receber compra")
        st.caption("Dá entrada no estoque, recalcula o custo médio e gera as contas a pagar.")
        data_recebimento = st.date_input(
            "Data do recebimento", value=hoje(), min_value=data_local(compra["data_pedido"]),
            max_value=hoje(), format="DD/MM/YYYY", key=f"receb_data_{compra_id}",
        )
        if st.button("Confirmar recebimento", type="primary", key=f"receber_{compra_id}"):
            try:
                resultado = compras.receber_compra(compra_id, data_recebimento, usuario["id"])
                avisar_apos_recarregar(
                    f"Pedido #{compra_id} recebido: {resultado['itens']} item(ns) no estoque e "
                    f"{resultado['parcelas']} parcela(s) em contas a pagar."
                )
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

        with st.expander("Editar pedido"):
            dados_edicao = editor_pedido(
                f"edit{compra_id}",
                {
                    "fornecedor_id": compra["fornecedor_id"],
                    "data_pedido": data_local(compra["data_pedido"]),
                    "num_parcelas": compra["num_parcelas"],
                    "primeiro_vencimento": compra["primeiro_vencimento"],
                    "observacao": compra["observacao"] or "",
                    "itens": [
                        {
                            "variacao_id": i["variacao_id"],
                            "quantidade": i["quantidade"],
                            "custo_unitario": float(i["custo_unitario"]),
                            "descricao": f"{i['sku']} | {i['produto']} | {i['tamanho']} | {i['cor']}",
                        }
                        for i in compra["itens"]
                    ],
                },
                "Salvar alterações",
            )
            if dados_edicao:
                try:
                    compras.atualizar_pedido(compra_id, **dados_edicao)
                    st.session_state.pop(f"carrinho_edit{compra_id}", None)
                    avisar_apos_recarregar("Pedido atualizado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))

        with st.expander("Cancelar pedido"):
            confirmar = st.checkbox("Confirmo o cancelamento deste pedido", key=f"cancelar_ok_{compra_id}")
            if st.button("Cancelar pedido", disabled=not confirmar, key=f"cancelar_{compra_id}"):
                try:
                    compras.cancelar_pedido(compra_id)
                    avisar_apos_recarregar(f"Pedido #{compra_id} cancelado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
