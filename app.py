"""Ponto de entrada: login, menu por perfil e execução da página."""
import streamlit as st

from config import APP_ICONE, APP_NOME, PERFIS, PERFIS_GESTAO
from services.auth_service import exigir_login

st.set_page_config(page_title=APP_NOME, page_icon=APP_ICONE, layout="wide")

usuario = exigir_login()
st.session_state["usuario"] = usuario

TODOS = PERFIS
GESTAO = PERFIS_GESTAO

# (seção, arquivo, título, ícone, perfis permitidos)
MENU = [
    ("Geral", "views/inicio.py", "Início", ":material/home:", TODOS),
    ("Cadastros", "views/produtos.py", "Produtos", ":material/checkroom:", TODOS),
    ("Cadastros", "views/clientes.py", "Clientes", ":material/person:", TODOS),
    ("Cadastros", "views/fornecedores.py", "Fornecedores", ":material/local_shipping:", GESTAO),
    ("Cadastros", "views/tabelas_auxiliares.py", "Tabelas auxiliares", ":material/tune:", GESTAO),
    ("Administração", "views/usuarios.py", "Usuários", ":material/group:", ("ADMIN",)),
]

secoes: dict[str, list] = {}
for secao, arquivo, titulo, icone, perfis in MENU:
    if usuario["perfil"] in perfis:
        secoes.setdefault(secao, []).append(
            st.Page(arquivo, title=titulo, icon=icone, default=(arquivo == "views/inicio.py"))
        )

pagina = st.navigation(secoes)

with st.sidebar:
    st.divider()
    st.caption(f"{usuario['nome']}  \n{usuario['perfil'].title()}")
    st.button("Sair", icon=":material/logout:", on_click=st.logout)

pagina.run()
