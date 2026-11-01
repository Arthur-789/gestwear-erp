"""Módulo Autenticação e Controle de Acesso: gestão de usuários."""
import pandas as pd
import streamlit as st

from config import PERFIS
from services import usuarios_service
from services.auth_service import exigir_perfil
from services.excecoes import RegraDeNegocioError
from utils.formatacao import fmt_datahora

ator = exigir_perfil("ADMIN")

st.title("Usuários")
st.caption("Somente e-mails cadastrados aqui conseguem entrar no sistema (login Google).")

aba_lista, aba_novo, aba_editar = st.tabs(["Lista", "Novo usuário", "Editar usuário"])
usuarios = usuarios_service.listar_usuarios()

with aba_lista:
    df = pd.DataFrame(
        [
            {
                "Nome": u["nome"],
                "E-mail": u["email"],
                "Perfil": u["perfil"].title(),
                "Situação": "Ativo" if u["ativo"] else "Inativo",
                "Cadastro": fmt_datahora(u["criado_em"]),
                "Último acesso": fmt_datahora(u["ultimo_login_em"]),
            }
            for u in usuarios
        ]
    )
    st.dataframe(df, hide_index=True, width="stretch")

with aba_novo:
    with st.form("form_novo_usuario", clear_on_submit=True):
        nome = st.text_input("Nome completo")
        email = st.text_input("E-mail Google")
        perfil = st.selectbox(
            "Perfil", PERFIS, index=PERFIS.index("VENDEDOR"), format_func=str.title
        )
        if st.form_submit_button("Cadastrar", type="primary"):
            try:
                usuarios_service.criar_usuario(email, nome, perfil)
                st.success("Usuário cadastrado.")
                st.rerun()
            except RegraDeNegocioError as e:
                st.error(str(e))

with aba_editar:
    escolhido = st.selectbox(
        "Usuário",
        usuarios,
        format_func=lambda u: f"{u['nome']} ({u['email']})",
        key="usuario_editar",
    )
    if escolhido:
        with st.form("form_editar_usuario"):
            nome_e = st.text_input("Nome completo", value=escolhido["nome"])
            st.text_input("E-mail", value=escolhido["email"], disabled=True)
            perfil_e = st.selectbox(
                "Perfil", PERFIS, index=PERFIS.index(escolhido["perfil"]), format_func=str.title
            )
            ativo_e = st.checkbox("Ativo", value=escolhido["ativo"])
            if st.form_submit_button("Salvar alterações", type="primary"):
                try:
                    usuarios_service.atualizar_usuario(
                        escolhido["id"], nome_e, perfil_e, ativo_e, ator["id"]
                    )
                    st.success("Usuário atualizado.")
                    st.rerun()
                except RegraDeNegocioError as e:
                    st.error(str(e))
