"""Regras de negócio do módulo Autenticação e Controle de Acesso."""
import re

import psycopg

from config import PERFIS
from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def listar_usuarios() -> list[dict]:
    return fetch_all(
        "SELECT id, nome, email, perfil, ativo, criado_em, ultimo_login_em "
        "FROM usuarios ORDER BY nome"
    )


def buscar_por_email(email: str) -> dict | None:
    return fetch_one(
        "SELECT id, nome, email, perfil, ativo FROM usuarios WHERE lower(email) = lower(%s)",
        (email.strip(),),
    )


def registrar_login(usuario_id: int) -> None:
    execute("UPDATE usuarios SET ultimo_login_em = now() WHERE id = %s", (usuario_id,))


def _validar(email: str, nome: str, perfil: str) -> tuple[str, str]:
    email = (email or "").strip().lower()
    nome = (nome or "").strip()
    if not _EMAIL_RE.match(email):
        raise RegraDeNegocioError("Informe um e-mail válido.")
    if len(nome) < 3:
        raise RegraDeNegocioError("Informe o nome (mínimo 3 caracteres).")
    if perfil not in PERFIS:
        raise RegraDeNegocioError("Perfil inválido.")
    return email, nome


def criar_usuario(email: str, nome: str, perfil: str) -> int:
    email, nome = _validar(email, nome, perfil)
    if buscar_por_email(email):
        raise RegraDeNegocioError("Já existe um usuário com este e-mail.")
    try:
        row = fetch_one(
            "INSERT INTO usuarios (email, nome, perfil) VALUES (%s, %s, %s) RETURNING id",
            (email, nome, perfil),
        )
    except psycopg.errors.UniqueViolation:
        raise RegraDeNegocioError("Já existe um usuário com este e-mail.")
    return row["id"]


def atualizar_usuario(
    usuario_id: int, nome: str, perfil: str, ativo: bool, ator_id: int
) -> None:
    """Atualiza nome, perfil e situação, evitando o bloqueio do sistema."""
    with transaction() as conn:
        antigo = fetch_one(
            "SELECT id, email, perfil FROM usuarios WHERE id = %s FOR UPDATE",
            (usuario_id,),
            conn,
        )
        if not antigo:
            raise RegraDeNegocioError("Usuário não encontrado.")
        _, nome = _validar(antigo["email"], nome, perfil)

        if usuario_id == ator_id:
            if not ativo:
                raise RegraDeNegocioError("Você não pode desativar o próprio usuário.")
            if antigo["perfil"] != perfil:
                raise RegraDeNegocioError("Você não pode alterar o próprio perfil.")

        execute(
            "UPDATE usuarios SET nome = %s, perfil = %s, ativo = %s WHERE id = %s",
            (nome, perfil, ativo, usuario_id),
            conn,
        )

        admins = fetch_one(
            "SELECT count(*) AS n FROM usuarios WHERE perfil = 'ADMIN' AND ativo",
            None,
            conn,
        )
        if admins["n"] < 1:
            # a exceção provoca o rollback da transação
            raise RegraDeNegocioError(
                "O sistema precisa manter ao menos um administrador ativo."
            )
