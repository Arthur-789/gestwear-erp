"""Exceções de domínio."""


class RegraDeNegocioError(Exception):
    """Violação de regra de negócio. A mensagem é exibida ao usuário."""
