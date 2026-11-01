"""Ponto de entrada: login, menu por perfil e execução da página."""
import streamlit as st

from config import APP_ICONE, APP_NOME
from services.auth_service import exigir_login

st.set_page_config(page_title=APP_NOME, page_icon=APP_ICONE, layout="wide")

usuario = exigir_login()
st.session_state["usuario"] = usuario

TODOS = ("ADMIN", "GERENTE", "VENDEDOR")
GESTAO = ("ADMIN", "GERENTE")

# (seção, arquivo, título, ícone, perfis permitidos)
MENU = [
    ("Geral", "pages/inicio.py", "Início", ":material/home:", TODOS),
    ("Administração", "pages/usuarios.py", "Usuários", ":material/group:", ("ADMIN",)),
]

secoes: dict[str, list] = {}
for secao, arquivo, titulo, icone, perfis in MENU:
    if usuario["perfil"] in perfis:
        secoes.setdefault(secao, []).append(
            st.Page(arquivo, title=titulo, icon=icone, default=(arquivo == "pages/inicio.py"))
        )

pagina = st.navigation(secoes)

with st.sidebar:
    st.divider()
    st.caption(f"{usuario['nome']}  \n{usuario['perfil'].title()}")
    st.button("Sair", icon=":material/logout:", on_click=st.logout)

pagina.run()
