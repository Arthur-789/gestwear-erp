"""Módulo Cadastro: fornecedores."""
import pandas as pd
import streamlit as st

from config import UFS
from services import fornecedores_service as fornecedores
from services.auth_service import exigir_perfil
from services.excecoes import RegraDeNegocioError
from utils.formatacao import fmt_cnpj, fmt_data, fmt_telefone, rotulo_situacao
from utils.ui import avisar_apos_recarregar, exibir_mensagens

exigir_perfil("ADMIN", "GERENTE")

st.title("Fornecedores")
exibir_mensagens()

aba_lista, aba_novo, aba_editar = st.tabs(["Lista", "Novo fornecedor", "Editar fornecedor"])

with aba_lista:
    c1, c2 = st.columns([3, 1])
    busca = c1.text_input("Buscar por razão social, contato ou CNPJ", key="for_busca")
    situacao = c2.selectbox("Situação", ["Todos", "Ativos", "Inativos"], key="for_situacao")
    ativo_filtro = {"Todos": None, "Ativos": True, "Inativos": False}[situacao]
    lista = fornecedores.listar_fornecedores(busca, ativo_filtro)
    if not lista:
        st.info("Nenhum fornecedor encontrado.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Razão social": f["razao_social"],
                        "CNPJ": fmt_cnpj(f["cnpj"]),
                        "Contato": f["contato"] or "",
                        "Telefone": fmt_telefone(f["telefone"]),
                        "E-mail": f["email"] or "",
                        "Cidade/UF": " / ".join(filter(None, [f["cidade"], f["uf"]])),
                        "Situação": rotulo_situacao(f["ativo"]),
                        "Cadastro": fmt_data(f["criado_em"]),
                    }
                    for f in lista
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with aba_novo:
    with st.form("form_novo_fornecedor", clear_on_submit=True):
        razao = st.text_input("Razão social")
        c1, c2 = st.columns(2)
        cnpj = c1.text_input("CNPJ")
        contato = c2.text_input("Pessoa de contato (opcional)")
        c3, c4 = st.columns(2)
        telefone = c3.text_input("Telefone com DDD (opcional)")
        email = c4.text_input("E-mail (opcional)")
        c5, c6 = st.columns([3, 1])
        cidade = c5.text_input("Cidade (opcional)")
        uf = c6.selectbox("UF", [""] + list(UFS))
        if st.form_submit_button("Cadastrar fornecedor", type="primary"):
            try:
                fornecedores.criar_fornecedor(razao, cnpj, contato, telefone, email, cidade, uf)
                avisar_apos_recarregar("Fornecedor cadastrado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

with aba_editar:
    todos = fornecedores.listar_fornecedores()
    if not todos:
        st.info("Nenhum fornecedor cadastrado.")
    else:
        por_id = {f["id"]: f for f in todos}
        fid = st.selectbox(
            "Fornecedor", list(por_id), format_func=lambda i: por_id[i]["razao_social"], key="for_editar"
        )
        f = por_id[fid]
        with st.form(f"form_editar_fornecedor_{fid}"):
            razao_e = st.text_input("Razão social", value=f["razao_social"])
            col1, col2 = st.columns(2)
            cnpj_e = col1.text_input("CNPJ", value=fmt_cnpj(f["cnpj"]))
            contato_e = col2.text_input("Pessoa de contato", value=f["contato"] or "")
            col3, col4 = st.columns(2)
            tel_e = col3.text_input("Telefone com DDD", value=fmt_telefone(f["telefone"]))
            email_e = col4.text_input("E-mail", value=f["email"] or "")
            col5, col6 = st.columns([3, 1])
            cidade_e = col5.text_input("Cidade", value=f["cidade"] or "")
            opcoes_uf = [""] + list(UFS)
            uf_e = col6.selectbox("UF", opcoes_uf, index=opcoes_uf.index(f["uf"] or ""))
            ativo_e = st.checkbox("Fornecedor ativo", value=f["ativo"])
            if st.form_submit_button("Salvar alterações", type="primary"):
                try:
                    fornecedores.atualizar_fornecedor(
                        fid, razao_e, cnpj_e, contato_e, tel_e, email_e, cidade_e, uf_e, ativo_e
                    )
                    avisar_apos_recarregar("Fornecedor atualizado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
