"""Exceções de domínio."""
from contextlib import contextmanager

import psycopg


class RegraDeNegocioError(Exception):
    """Violação de regra de negócio. A mensagem é exibida ao usuário."""


@contextmanager
def traduzir_erros_banco():
    """Converte violações de unicidade e de chave estrangeira em mensagens ao usuário."""
    try:
        yield
    except psycopg.errors.UniqueViolation as exc:
        raise RegraDeNegocioError("Já existe um registro com estes dados.") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise RegraDeNegocioError(
            "O registro está em uso por outros dados e não pode ser removido."
        ) from exc
