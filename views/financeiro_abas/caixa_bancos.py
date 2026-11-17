"""Aba Caixa e bancos: contas financeiras, saldos e extrato."""
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import streamlit as st

from services import tesouraria_service as tesouraria
from services.excecoes import RegraDeNegocioError
from utils.datas import hoje
from utils.formatacao import fmt_brl, fmt_datahora
from utils.ui import avisar_apos_recarregar


def _nova_conta() -> None:
    nonce = st.session_state.get("cx_nonce", 0)
    with st.expander("Nova conta"):
        c1, c2, c3 = st.columns([3, 1, 1])
        nome = c1.text_input("Nome", max_chars=80, key=f"cx{nonce}_nome")
        tipo = c2.selectbox(
            "Tipo", list(tesouraria.TIPOS_CONTA), format_func=lambda t: tesouraria.TIPOS_CONTA[t],
            key=f"cx{nonce}_tipo",
        )
        saldo = c3.number_input(
            "Saldo inicial (R$)", min_value=0.0, value=0.0, step=100.0, format="%.2f", key=f"cx{nonce}_saldo"
        )
        if st.button("Criar conta", type="primary", key=f"cx{nonce}_criar"):
            try:
                tesouraria.criar_conta(nome, tipo, saldo)
                st.session_state["cx_nonce"] = nonce + 1
                avisar_apos_recarregar("Conta criada.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))


def _editar_conta(contas: list[dict]) -> None:
    with st.expander("Editar conta"):
        por_id = {c["id"]: c for c in contas}
        conta_id = st.selectbox(
            "Conta", list(por_id), format_func=lambda i: por_id[i]["nome"], key="cx_editar_conta"
        )
        conta = por_id[conta_id]
        chave = f"cx_editar_{conta_id}"
        c1, c2 = st.columns([3, 1])
        nome = c1.text_input("Nome", value=conta["nome"], max_chars=80, key=f"{chave}_nome")
        ativa = c2.checkbox("Conta ativa", value=conta["ativa"], key=f"{chave}_ativa")
        tem_movimentos = conta["movimentos"] > 0
        saldo = st.number_input(
            "Saldo inicial (R$)", min_value=0.0, value=float(conta["saldo_inicial"]), step=100.0,
            format="%.2f", disabled=tem_movimentos, key=f"{chave}_saldo",
        )
        if tem_movimentos:
            st.caption("O saldo inicial não pode ser alterado depois da primeira movimentação.")
        if st.button("Salvar alterações", key=f"{chave}_salvar"):
            try:
                tesouraria.atualizar_conta(conta_id, nome, ativa, None if tem_movimentos else saldo)
                avisar_apos_recarregar("Conta atualizada.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))


def renderizar(usuario: dict) -> None:
    contas = tesouraria.listar_contas()
    ativas = [c for c in contas if c["ativa"]]
    st.metric(
        "Saldo total das contas ativas",
        fmt_brl(sum((c["saldo_atual"] for c in ativas), Decimal("0.00"))),
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Conta": c["nome"],
                    "Tipo": tesouraria.TIPOS_CONTA[c["tipo"]],
                    "Situação": "Ativa" if c["ativa"] else "Inativa",
                    "Saldo inicial": fmt_brl(c["saldo_inicial"]),
                    "Entradas": fmt_brl(c["entradas"]),
                    "Saídas": fmt_brl(c["saidas"]),
                    "Saldo atual": fmt_brl(c["saldo_atual"]),
                }
                for c in contas
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    _nova_conta()
    _editar_conta(contas)

    st.subheader("Extrato")
    por_id = {c["id"]: c["nome"] for c in contas}
    f1, f2, f3 = st.columns([2, 1, 1])
    conta_id = f1.selectbox(
        "Conta", [None] + list(por_id),
        format_func=lambda i: "Todas" if i is None else por_id[i], key="cx_extrato_conta",
    )
    data_de = f2.date_input("De", value=hoje() - timedelta(days=30), format="DD/MM/YYYY", key="cx_extrato_de")
    data_ate = f3.date_input("Até", value=hoje(), format="DD/MM/YYYY", key="cx_extrato_ate")

    totais = tesouraria.totais_extrato(conta_id, data_de, data_ate)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entradas", fmt_brl(totais["entradas"]))
    m2.metric("Saídas", fmt_brl(totais["saidas"]))
    m3.metric("Resultado do período", fmt_brl(totais["entradas"] - totais["saidas"]))
    m4.metric("Movimentações", totais["total"])

    limite = 500
    movimentos = tesouraria.extrato(conta_id, data_de, data_ate, limite=limite)
    if not movimentos:
        st.info("Nenhuma movimentação no período.")
        return
    if totais["total"] > limite:
        st.caption(f"Exibindo as {limite} movimentações mais recentes; os totais acima consideram todas.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Data": fmt_datahora(m["data_movimento"]),
                    "Conta": m["conta"],
                    "Tipo": tesouraria.TIPOS_MOVIMENTO[m["tipo"]],
                    "Valor": fmt_brl(m["valor"] if m["tipo"] == "ENTRADA" else -m["valor"]),
                    "Descrição": m["descricao"] or "-",
                    "Usuário": m["usuario"],
                    "Conciliada": "Sim" if m["conciliado"] else "Não",
                }
                for m in movimentos
            ]
        ),
        hide_index=True,
        width="stretch",
    )
