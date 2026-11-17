"""Aba Conciliação: confronto entre o saldo contábil e o saldo conciliado de cada conta."""
import pandas as pd
import streamlit as st

from services import tesouraria_service as tesouraria
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_datahora
from utils.ui import avisar_apos_recarregar


def _linha(m: dict) -> dict:
    return {
        "Data": fmt_datahora(m["data_movimento"]),
        "Tipo": tesouraria.TIPOS_MOVIMENTO[m["tipo"]],
        "Valor": fmt_brl(m["valor"] if m["tipo"] == "ENTRADA" else -m["valor"]),
        "Descrição": m["descricao"] or "-",
        "Usuário": m["usuario"],
        "Conciliada em": fmt_datahora(m["conciliado_em"]),
    }


def _rotulo(m: dict) -> str:
    sinal = "+" if m["tipo"] == "ENTRADA" else "-"
    return f"#{m['id']} | {fmt_datahora(m['data_movimento'])} | {sinal}{fmt_brl(m['valor'])} | {m['descricao'] or '-'}"


def renderizar(usuario: dict) -> None:
    contas = {c["id"]: c for c in tesouraria.listar_contas()}
    conta_id = st.selectbox(
        "Conta", list(contas), format_func=lambda i: contas[i]["nome"], key="conc_conta"
    )
    conta = contas[conta_id]
    nonce = st.session_state.get("conc_nonce", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo contábil", fmt_brl(conta["saldo_atual"]))
    m2.metric("Saldo conciliado", fmt_brl(conta["saldo_conciliado"]))
    m3.metric("Diferença", fmt_brl(conta["saldo_atual"] - conta["saldo_conciliado"]))
    m4.metric("Pendentes", conta["pendentes"])
    st.caption(
        "Concilie as movimentações que já conferem com o extrato do banco ou com a contagem do caixa. "
        "A diferença entre os saldos corresponde ao que ainda está pendente."
    )

    limite = 500
    pendentes = tesouraria.extrato(conta_id, conciliado=False, limite=limite)
    st.subheader("Pendentes de conciliação")
    if not pendentes:
        st.info("Nenhuma movimentação pendente nesta conta.")
    else:
        if conta["pendentes"] > limite:
            st.caption(f"Exibindo as {limite} movimentações mais recentes.")
        st.dataframe(
            pd.DataFrame([_linha(m) for m in pendentes]).drop(columns=["Conciliada em"]),
            hide_index=True,
            width="stretch",
        )
        por_id = {m["id"]: m for m in pendentes}
        c1, c2 = st.columns([4, 1])
        selecionadas = c1.multiselect(
            "Movimentações a conciliar", list(por_id), format_func=lambda i: _rotulo(por_id[i]),
            key=f"conc{nonce}_sel",
        )
        data = c2.date_input("Data", value=hoje(), max_value=hoje(), format="DD/MM/YYYY", key=f"conc{nonce}_data")
        b1, b2 = st.columns(2)
        todas = b2.checkbox("Confirmo conciliar todas as listadas", key=f"conc{nonce}_todas")
        acao = None
        if b1.button("Conciliar selecionadas", type="primary", key=f"conc{nonce}_conciliar", disabled=not selecionadas):
            acao = selecionadas
        if b2.button("Conciliar todas as listadas", key=f"conc{nonce}_conciliar_todas", disabled=not todas):
            acao = list(por_id)
        if acao:
            try:
                n = tesouraria.conciliar(acao, data)
                st.session_state["conc_nonce"] = nonce + 1
                avisar_apos_recarregar(f"{n} movimentação(ões) conciliada(s).")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

    conciliadas = tesouraria.extrato(conta_id, conciliado=True, limite=limite)
    with st.expander(f"Movimentações conciliadas ({len(conciliadas)})"):
        if not conciliadas:
            st.caption("Nenhuma movimentação conciliada.")
        else:
            st.dataframe(
                pd.DataFrame([_linha(m) for m in conciliadas]), hide_index=True, width="stretch"
            )
            por_id_c = {m["id"]: m for m in conciliadas}
            desfazer = st.multiselect(
                "Movimentações para desfazer a conciliação", list(por_id_c),
                format_func=lambda i: _rotulo(por_id_c[i]), key=f"conc{nonce}_desfazer",
            )
            if st.button("Desfazer conciliação", key=f"conc{nonce}_desfazer_btn", disabled=not desfazer):
                try:
                    n = tesouraria.desfazer_conciliacao(desfazer)
                    st.session_state["conc_nonce"] = nonce + 1
                    avisar_apos_recarregar(f"Conciliação desfeita em {n} movimentação(ões).")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
