"""Componentes auxiliares de interface."""
from pathlib import Path

import streamlit as st

from utils.formatacao import escapar_markdown

ASSETS = Path(__file__).resolve().parent.parent / "assets"

_CHAVE = "_mensagens_pendentes"
_EXIBIDORES = {"success": st.success, "warning": st.warning, "info": st.info}


def avisar_apos_recarregar(texto: str, tipo: str = "success") -> None:
    """Guarda uma mensagem para ser exibida após o st.rerun()."""
    st.session_state.setdefault(_CHAVE, []).append((tipo, texto))


def exibir_mensagens() -> None:
    for tipo, texto in st.session_state.pop(_CHAVE, []):
        _EXIBIDORES[tipo](escapar_markdown(texto))


def _tema_escuro() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def logo_marca(largura: int = 240) -> None:
    """Logo da marca, na versão adequada ao tema (claro ou escuro) em uso."""
    arquivo = "logo_escuro.svg" if _tema_escuro() else "logo_claro.svg"
    st.image(str(ASSETS / arquivo), width=largura)


def ilustracao_login(largura: int = 420) -> None:
    st.image(str(ASSETS / "ilustracao_login.svg"), width=largura)


def cabecalho(titulo: str, icone: str) -> None:
    """Título da página acompanhado do ícone temático (arquivo em assets/icones)."""
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        st.image(str(ASSETS / "icones" / f"{icone}.svg"), width=52)
        st.title(titulo)
