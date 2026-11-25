"""Aba Contas a pagar: lista, pagamento e despesas avulsas."""
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import contas_pagar_service as pagar
from services import fornecedores_service as fornecedores
from services.excecoes import RegraDeNegocioError
from utils.calculos import dividir_em_parcelas
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_brl_md, fmt_data, fmt_datahora
from utils.ui import avisar_apos_recarregar
from views.financeiro_abas.comum import formulario_baixa


def _nova_despesa(k: str) -> None:
    with st.expander("Nova despesa avulsa"):
        categorias = {c["id"]: c["nome"] for c in pagar.listar_categorias_despesa()}
        fornecedores_ativos = {f["id"]: f["razao_social"] for f in fornecedores.listar_fornecedores(ativo=True)}
        c1, c2 = st.columns([3, 2])
        descricao = c1.text_input("Descrição", max_chars=150, key=f"{k}_desc")
        categoria_id = c2.selectbox(
            "Categoria", list(categorias), format_func=lambda i: categorias[i], key=f"{k}_cat"
        )
        c3, c4, c5, c6 = st.columns(4)
        fornecedor_id = c3.selectbox(
            "Fornecedor (opcional)", [None] + list(fornecedores_ativos),
            format_func=lambda i: "Sem fornecedor" if i is None else fornecedores_ativos[i],
            key=f"{k}_forn",
        )
        valor = c4.number_input(
            "Valor total (R$)", min_value=0.0, value=0.0, step=10.0, format="%.2f", key=f"{k}_valor"
        )
        parcelas = c5.number_input("Parcelas", min_value=1, max_value=12, value=1, step=1, key=f"{k}_parc")
        vencimento = c6.date_input("1º vencimento", value=hoje(), format="DD/MM/YYYY", key=f"{k}_venc")
        if parcelas > 1 and valor >= 0.01 * parcelas:
            valores = dividir_em_parcelas(Decimal(str(valor)), int(parcelas))
            st.caption(
                f"{parcelas} parcelas mensais: {fmt_brl_md(valores[0])} cada"
                + (f" (a última de {fmt_brl_md(valores[-1])})" if valores[-1] != valores[0] else "")
                + "."
            )
        if st.button("Registrar despesa", type="primary", key=f"{k}_registrar"):
            try:
                ids = pagar.criar_despesa(
                    descricao, categoria_id, fornecedor_id, valor, int(parcelas), vencimento
                )
                st.session_state["pag_nonce"] = st.session_state.get("pag_nonce", 0) + 1
                st.session_state["pag_conta"] = ids[0]
                avisar_apos_recarregar(
                    f"Despesa registrada em {len(ids)} parcela(s). Veja em Contas a pagar."
                )
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))


def _editar_despesa(conta: dict) -> None:
    chave = f"pag_edit_{conta['id']}"
    categorias = {c["id"]: c["nome"] for c in pagar.listar_categorias_despesa()}
    fornecedores_ativos = {f["id"]: f["razao_social"] for f in fornecedores.listar_fornecedores(ativo=True)}
    if conta["categoria_id"] not in categorias:
        categorias[conta["categoria_id"]] = conta["categoria"]
    opcoes_fornecedor = [None] + list(fornecedores_ativos)
    if conta["fornecedor_id"] is not None and conta["fornecedor_id"] not in fornecedores_ativos:
        fornecedores_ativos[conta["fornecedor_id"]] = conta["favorecido"]
        opcoes_fornecedor.append(conta["fornecedor_id"])
    with st.expander("Editar despesa"):
        descricao = st.text_input("Descrição", value=conta["descricao"], max_chars=200, key=f"{chave}_desc")
        c1, c2 = st.columns(2)
        categoria_id = c1.selectbox(
            "Categoria", list(categorias), index=list(categorias).index(conta["categoria_id"]),
            format_func=lambda i: categorias[i], key=f"{chave}_cat",
        )
        fornecedor_id = c2.selectbox(
            "Fornecedor", opcoes_fornecedor, index=opcoes_fornecedor.index(conta["fornecedor_id"]),
            format_func=lambda i: "Sem fornecedor" if i is None else fornecedores_ativos[i],
            key=f"{chave}_forn",
        )
        c3, c4 = st.columns(2)
        valor = c3.number_input(
            "Valor (R$)", min_value=0.01, value=float(conta["valor"]), step=10.0, format="%.2f",
            key=f"{chave}_valor",
        )
        vencimento = c4.date_input(
            "Vencimento", value=conta["data_vencimento"], format="DD/MM/YYYY", key=f"{chave}_venc"
        )
        if st.button("Salvar alterações", key=f"{chave}_salvar"):
            try:
                pagar.atualizar_despesa(conta["id"], descricao, categoria_id, fornecedor_id, valor, vencimento)
                avisar_apos_recarregar("Despesa atualizada.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))
    with st.expander("Cancelar despesa"):
        st.caption("A despesa cancelada deixa de aparecer como conta em aberto. Esta ação não pode ser desfeita.")
        confirma = st.checkbox("Confirmo o cancelamento", key=f"pag_cancel_ok_{conta['id']}")
        if st.button("Cancelar despesa", key=f"pag_cancel_{conta['id']}", disabled=not confirma):
            try:
                pagar.cancelar_despesa(conta["id"])
                avisar_apos_recarregar("Despesa cancelada.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))


def renderizar(usuario: dict) -> None:
    nonce = st.session_state.get("pag_nonce", 0)
    _nova_despesa(f"pag{nonce}")

    categorias = {c["id"]: c["nome"] for c in pagar.listar_categorias()}
    f1, f2, f3, f4 = st.columns(4)
    situacao = f1.selectbox(
        "Situação", [None] + list(pagar.SITUACOES),
        format_func=lambda s: "Todas" if s is None else pagar.SITUACOES[s], key="pag_f_situacao",
    )
    origem = f2.selectbox(
        "Origem", [None] + list(pagar.ORIGENS),
        format_func=lambda o: "Todas" if o is None else pagar.ORIGENS[o], key="pag_f_origem",
    )
    categoria_id = f3.selectbox(
        "Categoria", [None] + list(categorias),
        format_func=lambda i: "Todas" if i is None else categorias[i], key="pag_f_categoria",
    )
    busca = f4.text_input("Buscar", placeholder="Descrição ou favorecido", key="pag_f_busca")
    f5, f6, _ = st.columns([1, 1, 2])
    venc_de = f5.date_input("Vencimento de", value=None, format="DD/MM/YYYY", key="pag_f_de")
    venc_ate = f6.date_input("Vencimento até", value=None, format="DD/MM/YYYY", key="pag_f_ate")

    filtros = (situacao, origem, categoria_id, busca, venc_de, venc_ate)
    totais = pagar.resumo(*filtros)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("A vencer", fmt_brl_md(totais["a_vencer"]))
    m2.metric("Vencido", fmt_brl_md(totais["vencido"]))
    m3.metric("Pago", fmt_brl_md(totais["pago"]))
    m4.metric("Contas", totais["total"])

    limite = 500
    lista = pagar.listar(*filtros, limite=limite)
    if not lista:
        st.info("Nenhuma conta a pagar encontrada.")
        return
    if totais["total"] > limite:
        st.caption(f"Exibindo as primeiras {limite} contas do filtro; os totais acima consideram todas.")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Nº": p["id"],
                    "Descrição": p["descricao"],
                    "Favorecido": p["favorecido"] or "-",
                    "Categoria": p["categoria"],
                    "Origem": pagar.ORIGENS[p["origem"]],
                    "Valor": fmt_brl(p["valor"]),
                    "Vencimento": fmt_data(p["data_vencimento"]),
                    "Situação": pagar.SITUACOES[p["situacao"]],
                    "Pago em": fmt_datahora(p["data_pagamento"]),
                    "Conta": p["conta"] or "-",
                }
                for p in lista
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Detalhe e pagamento")
    por_id = {p["id"]: p for p in lista}
    if st.session_state.get("pag_conta") not in por_id:
        st.session_state.pop("pag_conta", None)
    conta_id = st.selectbox(
        "Conta a pagar",
        list(por_id),
        format_func=lambda i: (
            f"#{i} | {por_id[i]['descricao']} | {fmt_data(por_id[i]['data_vencimento'])} | "
            f"{fmt_brl(por_id[i]['valor'])} | {pagar.SITUACOES[por_id[i]['situacao']]}"
        ),
        key="pag_conta",
    )
    conta = pagar.buscar(conta_id)
    st.caption(
        f"{pagar.ORIGENS[conta['origem']]} | Categoria: {conta['categoria']} | "
        f"Favorecido: {conta['favorecido'] or '-'} | Parcela {conta['num_parcela']}/{conta['total_parcelas']} | "
        f"Vencimento: {fmt_data(conta['data_vencimento'])} | Situação: {pagar.SITUACOES[conta['situacao']]}"
        + (f" | Origem em {fmt_data(conta['data_origem'])}" if conta["data_origem"] else "")
    )

    if conta["status"] == "ABERTA":
        clicou, conta_financeira_id, data = formulario_baixa(
            f"pag_baixa_{conta_id}", f"Registrar pagamento de {fmt_brl_md(conta['valor'])}",
            "Pagar com", conta["valor"], conta["data_origem"], saida=True,
        )
        if clicou:
            try:
                pagar.pagar(conta_id, conta_financeira_id, data, usuario["id"])
                avisar_apos_recarregar(f"Pagamento de {fmt_brl_md(conta['valor'])} registrado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))
        if conta["origem"] == "AVULSA":
            _editar_despesa(conta)
    elif conta["status"] == "PAGA":
        st.success(f"Paga em {fmt_datahora(conta['data_pagamento'])} ({conta['conta']}).")
    else:
        st.info("Conta cancelada.")
