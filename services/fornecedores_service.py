"""Regras de negócio do cadastro de fornecedores."""
from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import (
    cnpj_valido,
    escapar_like,
    normalizar_contato,
    somente_digitos,
    texto_opcional,
)

_COLUNAS = "id, razao_social, cnpj, contato, telefone, email, cidade, uf, ativo, criado_em"


def listar_fornecedores(busca: str | None = None, ativo: bool | None = None) -> list[dict]:
    condicoes, params = [], []
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        digitos = somente_digitos(busca)
        partes = ["razao_social ILIKE %s", "contato ILIKE %s"]
        params += [like, like]
        if digitos:
            partes.append("cnpj LIKE %s")
            params.append(f"%{digitos}%")
        condicoes.append("(" + " OR ".join(partes) + ")")
    if ativo is not None:
        condicoes.append("ativo = %s")
        params.append(ativo)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(f"SELECT {_COLUNAS} FROM fornecedores {where} ORDER BY razao_social", params)


def _validar(razao_social, cnpj, contato, telefone, email, cidade, uf) -> dict:
    razao = " ".join((razao_social or "").split())
    if len(razao) < 3:
        raise RegraDeNegocioError("Informe a razão social (mínimo 3 caracteres).")
    cnpj_digitos = somente_digitos(cnpj)
    if not cnpj_valido(cnpj_digitos):
        raise RegraDeNegocioError("CNPJ inválido.")
    tel, mail, sigla = normalizar_contato(telefone, email, uf)
    return {
        "razao_social": razao,
        "cnpj": cnpj_digitos,
        "contato": texto_opcional(contato),
        "telefone": tel,
        "email": mail,
        "cidade": texto_opcional(cidade),
        "uf": sigla,
    }


def _cnpj_em_uso(conn, cnpj: str, ignorar_id: int | None = None) -> bool:
    sql, params = "SELECT 1 FROM fornecedores WHERE cnpj = %s", [cnpj]
    if ignorar_id is not None:
        sql += " AND id <> %s"
        params.append(ignorar_id)
    return fetch_one(sql + " LIMIT 1", params, conn) is not None


def criar_fornecedor(razao_social, cnpj, contato, telefone, email, cidade, uf) -> int:
    d = _validar(razao_social, cnpj, contato, telefone, email, cidade, uf)
    with traduzir_erros_banco(), transaction() as conn:
        if _cnpj_em_uso(conn, d["cnpj"]):
            raise RegraDeNegocioError("Já existe um fornecedor com este CNPJ.")
        return fetch_one(
            "INSERT INTO fornecedores (razao_social, cnpj, contato, telefone, email, cidade, uf) "
            "VALUES (%(razao_social)s, %(cnpj)s, %(contato)s, %(telefone)s, %(email)s, "
            "%(cidade)s, %(uf)s) RETURNING id",
            d,
            conn,
        )["id"]


def atualizar_fornecedor(
    fornecedor_id: int, razao_social, cnpj, contato, telefone, email, cidade, uf, ativo: bool
) -> None:
    d = _validar(razao_social, cnpj, contato, telefone, email, cidade, uf)
    d.update(id=fornecedor_id, ativo=ativo)
    with traduzir_erros_banco(), transaction() as conn:
        existe = fetch_one(
            "SELECT 1 FROM fornecedores WHERE id = %s FOR UPDATE", (fornecedor_id,), conn
        )
        if not existe:
            raise RegraDeNegocioError("Fornecedor não encontrado.")
        if _cnpj_em_uso(conn, d["cnpj"], fornecedor_id):
            raise RegraDeNegocioError("Já existe outro fornecedor com este CNPJ.")
        execute(
            "UPDATE fornecedores SET razao_social = %(razao_social)s, cnpj = %(cnpj)s, "
            "contato = %(contato)s, telefone = %(telefone)s, email = %(email)s, "
            "cidade = %(cidade)s, uf = %(uf)s, ativo = %(ativo)s WHERE id = %(id)s",
            d,
            conn,
        )
