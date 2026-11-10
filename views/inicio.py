"""Página inicial: boas-vindas e verificação da conexão com o banco."""
import streamlit as st

from config import APP_NOME
from db.connection import fetch_one
from services.auth_service import usuario_atual

usuario = usuario_atual()
st.title(APP_NOME)
st.write(f"Olá, **{usuario['nome']}**. Perfil: **{usuario['perfil'].title()}**.")

st.subheader("Situação do sistema")
try:
    versao = fetch_one("SELECT version() AS v")["v"].split(",")[0]
    contagens = fetch_one(
        """
        SELECT (SELECT count(*) FROM usuarios)      AS usuarios,
               (SELECT count(*) FROM produtos)      AS produtos,
               (SELECT count(*) FROM clientes)      AS clientes,
               (SELECT count(*) FROM fornecedores)  AS fornecedores
        """
    )
    st.success(f"Banco de dados conectado ({versao}).")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Usuários", contagens["usuarios"])
    c2.metric("Produtos", contagens["produtos"])
    c3.metric("Clientes", contagens["clientes"])
    c4.metric("Fornecedores", contagens["fornecedores"])
except Exception as exc:
    st.error(f"Falha ao consultar o banco: {exc}")
