"""Componentes auxiliares de interface."""
import streamlit as st

_CHAVE = "_mensagens_pendentes"
_EXIBIDORES = {"success": st.success, "warning": st.warning, "info": st.info}


def avisar_apos_recarregar(texto: str, tipo: str = "success") -> None:
    """Guarda uma mensagem para ser exibida após o st.rerun()."""
    st.session_state.setdefault(_CHAVE, []).append((tipo, texto))


def exibir_mensagens() -> None:
    for tipo, texto in st.session_state.pop(_CHAVE, []):
        _EXIBIDORES[tipo](texto)
