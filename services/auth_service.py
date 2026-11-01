"""Autenticação (Google via st.login) e autorização por perfil."""
import streamlit as st

from config import APP_ICONE, APP_NOME
from services import usuarios_service


def _auth_configurado() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _tela_login() -> None:
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title(f"{APP_ICONE} {APP_NOME}")
        st.write("Acesso restrito a usuários autorizados.")
        if not _auth_configurado():
            st.error(
                "Login Google não configurado. Preencha a seção [auth] em "
                ".streamlit/secrets.toml (veja o README)."
            )
            return
        st.button("Entrar com Google", icon=":material/login:", on_click=st.login, type="primary")


def _tela_negado(email: str, motivo: str) -> None:
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title(f"{APP_ICONE} {APP_NOME}")
        st.error(f"Acesso negado para **{email}**. {motivo}")
        st.button("Sair", icon=":material/logout:", on_click=st.logout)


def exigir_login() -> dict:
    """Garante usuário autenticado e autorizado; interrompe a execução se não."""
    if not _auth_configurado() or not getattr(st.user, "is_logged_in", False):
        _tela_login()
        st.stop()

    email = (st.user.get("email") or "").strip().lower()
    if not email or not st.user.get("email_verified", True):
        _tela_negado(email or "(sem e-mail)", "O e-mail Google não está verificado.")
        st.stop()

    usuario = usuarios_service.buscar_por_email(email)
    if usuario is None:
        _tela_negado(email, "Este e-mail não está cadastrado. Peça a um administrador.")
        st.stop()
    if not usuario["ativo"]:
        _tela_negado(email, "Seu usuário está desativado.")
        st.stop()

    if not st.session_state.get("_login_registrado"):
        usuarios_service.registrar_login(usuario["id"])
        st.session_state["_login_registrado"] = True
    return usuario


def usuario_atual() -> dict:
    return st.session_state["usuario"]


def exigir_perfil(*perfis: str) -> dict:
    """Interrompe a página se o perfil do usuário não estiver entre os permitidos."""
    usuario = usuario_atual()
    if usuario["perfil"] not in perfis:
        st.error("Você não tem permissão para acessar esta página.")
        st.stop()
    return usuario
