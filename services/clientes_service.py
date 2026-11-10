"""Regras de negócio do cadastro de clientes."""
from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import (
    cpf_valido,
    escapar_like,
    normalizar_contato,
    somente_digitos,
    texto_opcional,
)

_COLUNAS = "id, nome, cpf, telefone, email, cidade, uf, ativo, criado_em"


def listar_clientes(busca: str | None = None, ativo: bool | None = None) -> list[dict]:
    condicoes, params = [], []
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        digitos = somente_digitos(busca)
        partes = ["nome ILIKE %s", "email ILIKE %s"]
        params += [like, like]
        if digitos:
            partes.append("cpf LIKE %s")
            params.append(f"%{digitos}%")
        condicoes.append("(" + " OR ".join(partes) + ")")
    if ativo is not None:
        condicoes.append("ativo = %s")
        params.append(ativo)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(f"SELECT {_COLUNAS} FROM clientes {where} ORDER BY nome", params)


def _validar(nome, cpf, telefone, email, cidade, uf) -> dict:
    nome = " ".join((nome or "").split())
    if len(nome) < 3:
        raise RegraDeNegocioError("Informe o nome do cliente (mínimo 3 caracteres).")
    cpf_digitos = somente_digitos(cpf) or None
    if cpf_digitos and not cpf_valido(cpf_digitos):
        raise RegraDeNegocioError("CPF inválido.")
    tel, mail, sigla = normalizar_contato(telefone, email, uf)
    return {
        "nome": nome,
        "cpf": cpf_digitos,
        "telefone": tel,
        "email": mail,
        "cidade": texto_opcional(cidade),
        "uf": sigla,
    }


def _cpf_em_uso(conn, cpf: str | None, ignorar_id: int | None = None) -> bool:
    if not cpf:
        return False
    sql, params = "SELECT 1 FROM clientes WHERE cpf = %s", [cpf]
    if ignorar_id is not None:
        sql += " AND id <> %s"
        params.append(ignorar_id)
    return fetch_one(sql + " LIMIT 1", params, conn) is not None


def criar_cliente(nome, cpf, telefone, email, cidade, uf) -> int:
    d = _validar(nome, cpf, telefone, email, cidade, uf)
    with traduzir_erros_banco(), transaction() as conn:
        if _cpf_em_uso(conn, d["cpf"]):
            raise RegraDeNegocioError("Já existe um cliente com este CPF.")
        return fetch_one(
            "INSERT INTO clientes (nome, cpf, telefone, email, cidade, uf) "
            "VALUES (%(nome)s, %(cpf)s, %(telefone)s, %(email)s, %(cidade)s, %(uf)s) RETURNING id",
            d,
            conn,
        )["id"]


def atualizar_cliente(cliente_id: int, nome, cpf, telefone, email, cidade, uf, ativo: bool) -> None:
    d = _validar(nome, cpf, telefone, email, cidade, uf)
    d.update(id=cliente_id, ativo=ativo)
    with traduzir_erros_banco(), transaction() as conn:
        existe = fetch_one("SELECT 1 FROM clientes WHERE id = %s FOR UPDATE", (cliente_id,), conn)
        if not existe:
            raise RegraDeNegocioError("Cliente não encontrado.")
        if _cpf_em_uso(conn, d["cpf"], cliente_id):
            raise RegraDeNegocioError("Já existe outro cliente com este CPF.")
        execute(
            "UPDATE clientes SET nome = %(nome)s, cpf = %(cpf)s, telefone = %(telefone)s, "
            "email = %(email)s, cidade = %(cidade)s, uf = %(uf)s, ativo = %(ativo)s "
            "WHERE id = %(id)s",
            d,
            conn,
        )
