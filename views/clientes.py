"""Módulo Cadastro: clientes."""
import pandas as pd
import streamlit as st

from config import UFS
from services import clientes_service as clientes
from services.excecoes import RegraDeNegocioError
from utils.formatacao import fmt_cpf, fmt_data, fmt_telefone, rotulo_situacao
from utils.ui import avisar_apos_recarregar, exibir_mensagens

st.title("Clientes")
exibir_mensagens()

aba_lista, aba_novo, aba_editar = st.tabs(["Lista", "Novo cliente", "Editar cliente"])

with aba_lista:
    c1, c2 = st.columns([3, 1])
    busca = c1.text_input("Buscar por nome, CPF ou e-mail", key="cli_busca")
    situacao = c2.selectbox("Situação", ["Todos", "Ativos", "Inativos"], key="cli_situacao")
    ativo_filtro = {"Todos": None, "Ativos": True, "Inativos": False}[situacao]
    lista = clientes.listar_clientes(busca, ativo_filtro)
    if not lista:
        st.info("Nenhum cliente encontrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Nome": c["nome"],
                        "CPF": fmt_cpf(c["cpf"]),
                        "Telefone": fmt_telefone(c["telefone"]),
                        "E-mail": c["email"] or "",
                        "Cidade/UF": " / ".join(filter(None, [c["cidade"], c["uf"]])),
                        "Situação": rotulo_situacao(c["ativo"]),
                        "Cadastro": fmt_data(c["criado_em"]),
                    }
                    for c in lista
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with aba_novo:
    with st.form("form_novo_cliente", clear_on_submit=True):
        nome = st.text_input("Nome completo")
        c1, c2 = st.columns(2)
        cpf = c1.text_input("CPF (opcional)")
        telefone = c2.text_input("Telefone com DDD (opcional)")
        email = st.text_input("E-mail (opcional)")
        c3, c4 = st.columns([3, 1])
        cidade = c3.text_input("Cidade (opcional)")
        uf = c4.selectbox("UF", [""] + list(UFS))
        if st.form_submit_button("Cadastrar cliente", type="primary"):
            try:
                clientes.criar_cliente(nome, cpf, telefone, email, cidade, uf)
                avisar_apos_recarregar("Cliente cadastrado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

with aba_editar:
    todos = clientes.listar_clientes()
    if not todos:
        st.info("Nenhum cliente cadastrado.")
    else:
        por_id = {c["id"]: c for c in todos}
        cid = st.selectbox(
            "Cliente", list(por_id), format_func=lambda i: por_id[i]["nome"], key="cli_editar"
        )
        c = por_id[cid]
        with st.form(f"form_editar_cliente_{cid}"):
            nome_e = st.text_input("Nome completo", value=c["nome"])
            col1, col2 = st.columns(2)
            cpf_e = col1.text_input("CPF", value=fmt_cpf(c["cpf"]))
            tel_e = col2.text_input("Telefone com DDD", value=fmt_telefone(c["telefone"]))
            email_e = st.text_input("E-mail", value=c["email"] or "")
            col3, col4 = st.columns([3, 1])
            cidade_e = col3.text_input("Cidade", value=c["cidade"] or "")
            opcoes_uf = [""] + list(UFS)
            uf_e = col4.selectbox("UF", opcoes_uf, index=opcoes_uf.index(c["uf"] or ""))
            ativo_e = st.checkbox("Cliente ativo", value=c["ativo"])
            if st.form_submit_button("Salvar alterações", type="primary"):
                try:
                    clientes.atualizar_cliente(
                        cid, nome_e, cpf_e, tel_e, email_e, cidade_e, uf_e, ativo_e
                    )
                    avisar_apos_recarregar("Cliente atualizado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
