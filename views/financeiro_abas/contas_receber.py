"""Aba Contas a receber: lista e recebimento de parcelas."""
import pandas as pd
import streamlit as st

from services import clientes_service as clientes
from services import contas_receber_service as receber
from services.excecoes import RegraDeNegocioError
from utils.formatacao import fmt_brl, fmt_brl_md, fmt_data, fmt_datahora
from utils.ui import avisar_apos_recarregar
from views.financeiro_abas.comum import formulario_baixa


def _origem(r: dict) -> str:
    return f"Venda #{r['venda_id']}" if r["venda_id"] else f"Troca #{r['troca_devolucao_id']}"


def renderizar(usuario: dict) -> None:
    nomes = {c["id"]: c["nome"] for c in clientes.listar_clientes()}
    f1, f2, f3, f4 = st.columns(4)
    situacao = f1.selectbox(
        "Situação", [None] + list(receber.SITUACOES),
        format_func=lambda s: "Todas" if s is None else receber.SITUACOES[s], key="rec_f_situacao",
    )
    origem = f2.selectbox(
        "Origem", [None] + list(receber.ORIGENS),
        format_func=lambda o: "Todas" if o is None else receber.ORIGENS[o], key="rec_f_origem",
    )
    cliente_id = f3.selectbox(
        "Cliente", [None] + list(nomes),
        format_func=lambda i: "Todos" if i is None else nomes[i], key="rec_f_cliente",
    )
    f5, f6 = f4.columns(2)
    venc_de = f5.date_input("Venc. de", value=None, format="DD/MM/YYYY", key="rec_f_de")
    venc_ate = f6.date_input("Venc. até", value=None, format="DD/MM/YYYY", key="rec_f_ate")

    filtros = (situacao, origem, cliente_id, None, venc_de, venc_ate)
    totais = receber.resumo(*filtros)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("A vencer", fmt_brl_md(totais["a_vencer"]))
    m2.metric("Vencido", fmt_brl_md(totais["vencido"]))
    m3.metric("Recebido", fmt_brl_md(totais["recebido"]))
    m4.metric("Contas", totais["total"])

    limite = 500
    lista = receber.listar(*filtros, limite=limite)
    if not lista:
        st.info("Nenhuma conta a receber encontrada.")
        return
    if totais["total"] > limite:
        st.caption(f"Exibindo as primeiras {limite} contas do filtro; os totais acima consideram todas.")

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Nº": r["id"],
                    "Cliente": r["cliente"] or "Consumidor final",
                    "Origem": _origem(r),
                    "Parcela": f"{r['num_parcela']}/{r['total_parcelas']}",
                    "Valor": fmt_brl(r["valor"]),
                    "Vencimento": fmt_data(r["data_vencimento"]),
                    "Situação": receber.SITUACOES[r["situacao"]],
                    "Recebida em": fmt_datahora(r["data_recebimento"]),
                    "Conta": r["conta"] or "-",
                }
                for r in lista
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Detalhe e recebimento")
    por_id = {r["id"]: r for r in lista}
    if st.session_state.get("rec_conta") not in por_id:
        st.session_state.pop("rec_conta", None)
    conta_id = st.selectbox(
        "Conta a receber",
        list(por_id),
        format_func=lambda i: (
            f"#{i} | {por_id[i]['cliente'] or 'Consumidor final'} | {_origem(por_id[i])} "
            f"({por_id[i]['num_parcela']}/{por_id[i]['total_parcelas']}) | "
            f"{fmt_data(por_id[i]['data_vencimento'])} | {fmt_brl(por_id[i]['valor'])} | "
            f"{receber.SITUACOES[por_id[i]['situacao']]}"
        ),
        key="rec_conta",
    )
    conta = receber.buscar(conta_id)
    st.caption(
        f"{_origem(conta)} em {fmt_data(conta['data_origem'])} | Categoria: {conta['categoria']} | "
        f"Cliente: {conta['cliente'] or 'Consumidor final'} | Vencimento: {fmt_data(conta['data_vencimento'])} | "
        f"Situação: {receber.SITUACOES[conta['situacao']]}"
    )

    if conta["status"] == "ABERTA":
        clicou, conta_financeira_id, data = formulario_baixa(
            f"rec_baixa_{conta_id}", f"Registrar recebimento de {fmt_brl_md(conta['valor'])}",
            "Receber em", conta["valor"], conta["data_origem"], saida=False,
        )
        if clicou:
            try:
                receber.receber(conta_id, conta_financeira_id, data, usuario["id"])
                avisar_apos_recarregar(f"Recebimento de {fmt_brl_md(conta['valor'])} registrado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))
    elif conta["status"] == "RECEBIDA":
        st.success(f"Recebida em {fmt_datahora(conta['data_recebimento'])} ({conta['conta']}).")
    else:
        st.info("Conta cancelada.")
