"""Regras de negócio do módulo Cadastro: categorias, tamanhos, cores, produtos e variações."""
import re
from decimal import Decimal, InvalidOperation

from db.connection import execute, fetch_all, fetch_one, transaction
from services.excecoes import RegraDeNegocioError, traduzir_erros_banco
from services.validadores import escapar_like, texto_opcional
from utils.formatacao import fmt_brl

_COD_CATEGORIA = re.compile(r"[A-Z0-9]{2,5}")
_COD_COR = re.compile(r"[A-Z0-9]{1,4}")
_NOME_TAMANHO = re.compile(r"[A-Z0-9]{1,5}")
_LIMITE_VALOR = Decimal("10000000000")


# ---------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------
def _nome(valor: str | None, rotulo: str, minimo: int = 2, maximo: int = 80) -> str:
    nome = " ".join((valor or "").split())
    if len(nome) < minimo:
        raise RegraDeNegocioError(f"Informe o {rotulo} (mínimo {minimo} caracteres).")
    if len(nome) > maximo:
        raise RegraDeNegocioError(f"O {rotulo} deve ter no máximo {maximo} caracteres.")
    return nome


def _codigo(valor: str | None, padrao: re.Pattern, rotulo: str, dica: str) -> str:
    codigo = (valor or "").strip().upper()
    if not padrao.fullmatch(codigo):
        raise RegraDeNegocioError(f"O {rotulo} deve ter {dica}, só com letras e números.")
    return codigo


def _preco(valor, rotulo: str) -> Decimal:
    if valor is None or valor == "":
        raise RegraDeNegocioError(f"Informe o {rotulo}.")
    try:
        preco = Decimal(str(valor)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise RegraDeNegocioError(f"{rotulo.capitalize()} inválido.")
    if preco <= 0:
        raise RegraDeNegocioError(f"O {rotulo} deve ser maior que zero.")
    if preco >= _LIMITE_VALOR:
        raise RegraDeNegocioError(f"O {rotulo} excede o valor máximo permitido.")
    return preco


def _inteiro(valor, rotulo: str, maximo: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise RegraDeNegocioError(f"Informe {rotulo}.")
    if numero < 0 or numero > maximo:
        raise RegraDeNegocioError(f"{rotulo.capitalize()} deve estar entre 0 e {maximo}.")
    return numero


def _existe(conn, tabela: str, coluna: str, valor: str, ignorar_id: int | None = None) -> bool:
    """Verifica duplicidade sem diferenciar maiúsculas de minúsculas (tabela/coluna fixas no código)."""
    sql = f"SELECT 1 FROM {tabela} WHERE lower({coluna}) = lower(%s)"
    params = [valor]
    if ignorar_id is not None:
        sql += " AND id <> %s"
        params.append(ignorar_id)
    return fetch_one(sql + " LIMIT 1", params, conn) is not None


def _variacoes_usam(conn, filtro_sql: str, valor: int) -> bool:
    row = fetch_one(
        f"SELECT EXISTS (SELECT 1 FROM produto_variacoes v "
        f"JOIN produtos p ON p.id = v.produto_id WHERE {filtro_sql}) AS usado",
        (valor,),
        conn,
    )
    return row["usado"]


# ---------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------
def listar_categorias(somente_ativas: bool = False) -> list[dict]:
    filtro = "WHERE c.ativo" if somente_ativas else ""
    return fetch_all(
        f"""
        SELECT c.id, c.nome, c.codigo, c.ativo,
               (SELECT count(*) FROM produtos p WHERE p.categoria_id = c.id) AS produtos
          FROM categorias c {filtro}
         ORDER BY c.nome
        """
    )


def criar_categoria(nome: str, codigo: str) -> int:
    nome = _nome(nome, "nome da categoria")
    codigo = _codigo(codigo, _COD_CATEGORIA, "código da categoria", "de 2 a 5 caracteres")
    with traduzir_erros_banco(), transaction() as conn:
        if _existe(conn, "categorias", "nome", nome):
            raise RegraDeNegocioError("Já existe uma categoria com este nome.")
        if _existe(conn, "categorias", "codigo", codigo):
            raise RegraDeNegocioError("Já existe uma categoria com este código.")
        return fetch_one(
            "INSERT INTO categorias (nome, codigo) VALUES (%s, %s) RETURNING id",
            (nome, codigo),
            conn,
        )["id"]


def atualizar_categoria(categoria_id: int, nome: str, codigo: str, ativo: bool) -> None:
    nome = _nome(nome, "nome da categoria")
    codigo = _codigo(codigo, _COD_CATEGORIA, "código da categoria", "de 2 a 5 caracteres")
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT codigo FROM categorias WHERE id = %s FOR UPDATE", (categoria_id,), conn
        )
        if not atual:
            raise RegraDeNegocioError("Categoria não encontrada.")
        if _existe(conn, "categorias", "nome", nome, categoria_id):
            raise RegraDeNegocioError("Já existe uma categoria com este nome.")
        if _existe(conn, "categorias", "codigo", codigo, categoria_id):
            raise RegraDeNegocioError("Já existe uma categoria com este código.")
        if codigo != atual["codigo"] and _variacoes_usam(conn, "p.categoria_id = %s", categoria_id):
            raise RegraDeNegocioError(
                "O código não pode ser alterado: há SKUs gerados com esta categoria."
            )
        execute(
            "UPDATE categorias SET nome = %s, codigo = %s, ativo = %s WHERE id = %s",
            (nome, codigo, ativo, categoria_id),
            conn,
        )


# ---------------------------------------------------------------------
# Tamanhos
# ---------------------------------------------------------------------
def listar_tamanhos() -> list[dict]:
    return fetch_all(
        """
        SELECT t.id, t.nome, t.ordem,
               (SELECT count(*) FROM produto_variacoes v WHERE v.tamanho_id = t.id) AS variacoes
          FROM tamanhos t
         ORDER BY t.ordem, t.nome
        """
    )


def criar_tamanho(nome: str, ordem: int) -> int:
    nome = _codigo(nome, _NOME_TAMANHO, "nome do tamanho", "de 1 a 5 caracteres")
    ordem = _inteiro(ordem, "a ordem de exibição", 999)
    with traduzir_erros_banco(), transaction() as conn:
        if _existe(conn, "tamanhos", "nome", nome):
            raise RegraDeNegocioError("Já existe um tamanho com este nome.")
        return fetch_one(
            "INSERT INTO tamanhos (nome, ordem) VALUES (%s, %s) RETURNING id",
            (nome, ordem),
            conn,
        )["id"]


def atualizar_tamanho(tamanho_id: int, nome: str, ordem: int) -> None:
    nome = _codigo(nome, _NOME_TAMANHO, "nome do tamanho", "de 1 a 5 caracteres")
    ordem = _inteiro(ordem, "a ordem de exibição", 999)
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT nome FROM tamanhos WHERE id = %s FOR UPDATE", (tamanho_id,), conn
        )
        if not atual:
            raise RegraDeNegocioError("Tamanho não encontrado.")
        if _existe(conn, "tamanhos", "nome", nome, tamanho_id):
            raise RegraDeNegocioError("Já existe um tamanho com este nome.")
        if nome != atual["nome"]:
            em_uso = fetch_one(
                "SELECT EXISTS (SELECT 1 FROM produto_variacoes WHERE tamanho_id = %s) AS usado",
                (tamanho_id,),
                conn,
            )["usado"]
            if em_uso:
                raise RegraDeNegocioError(
                    "O nome não pode ser alterado: há SKUs gerados com este tamanho."
                )
        execute(
            "UPDATE tamanhos SET nome = %s, ordem = %s WHERE id = %s",
            (nome, ordem, tamanho_id),
            conn,
        )


def excluir_tamanho(tamanho_id: int) -> None:
    with traduzir_erros_banco(), transaction() as conn:
        removidos = execute("DELETE FROM tamanhos WHERE id = %s", (tamanho_id,), conn)
        if not removidos:
            raise RegraDeNegocioError("Tamanho não encontrado.")


# ---------------------------------------------------------------------
# Cores
# ---------------------------------------------------------------------
def listar_cores() -> list[dict]:
    return fetch_all(
        """
        SELECT c.id, c.nome, c.codigo,
               (SELECT count(*) FROM produto_variacoes v WHERE v.cor_id = c.id) AS variacoes
          FROM cores c
         ORDER BY c.nome
        """
    )


def criar_cor(nome: str, codigo: str) -> int:
    nome = _nome(nome, "nome da cor", maximo=40)
    codigo = _codigo(codigo, _COD_COR, "código da cor", "de 1 a 4 caracteres")
    with traduzir_erros_banco(), transaction() as conn:
        if _existe(conn, "cores", "nome", nome):
            raise RegraDeNegocioError("Já existe uma cor com este nome.")
        if _existe(conn, "cores", "codigo", codigo):
            raise RegraDeNegocioError("Já existe uma cor com este código.")
        return fetch_one(
            "INSERT INTO cores (nome, codigo) VALUES (%s, %s) RETURNING id",
            (nome, codigo),
            conn,
        )["id"]


def atualizar_cor(cor_id: int, nome: str, codigo: str) -> None:
    nome = _nome(nome, "nome da cor", maximo=40)
    codigo = _codigo(codigo, _COD_COR, "código da cor", "de 1 a 4 caracteres")
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one("SELECT codigo FROM cores WHERE id = %s FOR UPDATE", (cor_id,), conn)
        if not atual:
            raise RegraDeNegocioError("Cor não encontrada.")
        if _existe(conn, "cores", "nome", nome, cor_id):
            raise RegraDeNegocioError("Já existe uma cor com este nome.")
        if _existe(conn, "cores", "codigo", codigo, cor_id):
            raise RegraDeNegocioError("Já existe uma cor com este código.")
        if codigo != atual["codigo"]:
            em_uso = fetch_one(
                "SELECT EXISTS (SELECT 1 FROM produto_variacoes WHERE cor_id = %s) AS usado",
                (cor_id,),
                conn,
            )["usado"]
            if em_uso:
                raise RegraDeNegocioError(
                    "O código não pode ser alterado: há SKUs gerados com esta cor."
                )
        execute(
            "UPDATE cores SET nome = %s, codigo = %s WHERE id = %s",
            (nome, codigo, cor_id),
            conn,
        )


def excluir_cor(cor_id: int) -> None:
    with traduzir_erros_banco(), transaction() as conn:
        removidos = execute("DELETE FROM cores WHERE id = %s", (cor_id,), conn)
        if not removidos:
            raise RegraDeNegocioError("Cor não encontrada.")


# ---------------------------------------------------------------------
# Produtos
# ---------------------------------------------------------------------
def listar_produtos(
    busca: str | None = None, categoria_id: int | None = None, ativo: bool | None = None
) -> list[dict]:
    condicoes, params = [], []
    if busca and busca.strip():
        like = f"%{escapar_like(busca.strip())}%"
        condicoes.append(
            "(p.nome ILIKE %s OR EXISTS (SELECT 1 FROM produto_variacoes x "
            "WHERE x.produto_id = p.id AND x.sku ILIKE %s))"
        )
        params += [like, like]
    if categoria_id is not None:
        condicoes.append("p.categoria_id = %s")
        params.append(categoria_id)
    if ativo is not None:
        condicoes.append("p.ativo = %s")
        params.append(ativo)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    return fetch_all(
        f"""
        SELECT p.id, p.nome, p.descricao, p.ativo, p.categoria_id, c.nome AS categoria,
               count(v.id) AS variacoes,
               coalesce(sum(v.estoque_atual), 0) AS estoque_total,
               min(v.preco_venda) AS preco_min, max(v.preco_venda) AS preco_max
          FROM produtos p
          JOIN categorias c ON c.id = p.categoria_id
          LEFT JOIN produto_variacoes v ON v.produto_id = p.id
          {where}
         GROUP BY p.id, c.nome
         ORDER BY p.nome
        """,
        params,
    )


def buscar_produto(produto_id: int) -> dict | None:
    return fetch_one(
        """
        SELECT p.id, p.nome, p.descricao, p.ativo, p.categoria_id,
               c.nome AS categoria, c.codigo AS codigo_categoria
          FROM produtos p JOIN categorias c ON c.id = p.categoria_id
         WHERE p.id = %s
        """,
        (produto_id,),
    )


def criar_produto(nome: str, descricao: str | None, categoria_id: int) -> int:
    nome = _nome(nome, "nome do produto", maximo=150)
    descricao = texto_opcional(descricao)
    with traduzir_erros_banco(), transaction() as conn:
        categoria = fetch_one(
            "SELECT ativo FROM categorias WHERE id = %s", (categoria_id,), conn
        )
        if not categoria:
            raise RegraDeNegocioError("Selecione a categoria do produto.")
        if not categoria["ativo"]:
            raise RegraDeNegocioError("A categoria selecionada está inativa.")
        if _existe(conn, "produtos", "nome", nome):
            raise RegraDeNegocioError("Já existe um produto com este nome.")
        return fetch_one(
            "INSERT INTO produtos (nome, descricao, categoria_id) VALUES (%s, %s, %s) RETURNING id",
            (nome, descricao, categoria_id),
            conn,
        )["id"]


def atualizar_produto(
    produto_id: int, nome: str, descricao: str | None, categoria_id: int, ativo: bool
) -> None:
    nome = _nome(nome, "nome do produto", maximo=150)
    descricao = texto_opcional(descricao)
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT categoria_id FROM produtos WHERE id = %s FOR UPDATE", (produto_id,), conn
        )
        if not atual:
            raise RegraDeNegocioError("Produto não encontrado.")
        if _existe(conn, "produtos", "nome", nome, produto_id):
            raise RegraDeNegocioError("Já existe um produto com este nome.")
        if categoria_id != atual["categoria_id"]:
            categoria = fetch_one(
                "SELECT ativo FROM categorias WHERE id = %s", (categoria_id,), conn
            )
            if not categoria or not categoria["ativo"]:
                raise RegraDeNegocioError("Selecione uma categoria ativa.")
            tem_variacoes = fetch_one(
                "SELECT EXISTS (SELECT 1 FROM produto_variacoes WHERE produto_id = %s) AS usado",
                (produto_id,),
                conn,
            )["usado"]
            if tem_variacoes:
                raise RegraDeNegocioError(
                    "A categoria não pode ser alterada: o produto já tem variações (SKUs)."
                )
        execute(
            "UPDATE produtos SET nome = %s, descricao = %s, categoria_id = %s, ativo = %s "
            "WHERE id = %s",
            (nome, descricao, categoria_id, ativo, produto_id),
            conn,
        )


# ---------------------------------------------------------------------
# Variações (SKU)
# ---------------------------------------------------------------------
def listar_variacoes(produto_id: int) -> list[dict]:
    return fetch_all(
        """
        SELECT v.id, v.sku, v.tamanho_id, t.nome AS tamanho, v.cor_id, c.nome AS cor,
               v.preco_venda, v.custo_medio, v.estoque_atual, v.estoque_minimo, v.ativo
          FROM produto_variacoes v
          JOIN tamanhos t ON t.id = v.tamanho_id
          JOIN cores c ON c.id = v.cor_id
         WHERE v.produto_id = %s
         ORDER BY t.ordem, c.nome
        """,
        (produto_id,),
    )


def criar_variacao(
    produto_id: int, tamanho_id: int, cor_id: int, preco_venda, estoque_minimo
) -> dict:
    """Cria a variação e gera o SKU no formato CATEGORIA-0001-TAMANHO-COR."""
    preco = _preco(preco_venda, "preço de venda")
    minimo = _inteiro(estoque_minimo, "o estoque mínimo", 100000)
    with traduzir_erros_banco(), transaction() as conn:
        produto = fetch_one(
            """
            SELECT p.id, p.ativo, c.codigo
              FROM produtos p JOIN categorias c ON c.id = p.categoria_id
             WHERE p.id = %s
               FOR UPDATE OF p
            """,
            (produto_id,),
            conn,
        )
        if not produto:
            raise RegraDeNegocioError("Produto não encontrado.")
        if not produto["ativo"]:
            raise RegraDeNegocioError("Não é possível adicionar variações a um produto inativo.")
        tamanho = fetch_one("SELECT nome FROM tamanhos WHERE id = %s", (tamanho_id,), conn)
        cor = fetch_one("SELECT codigo FROM cores WHERE id = %s", (cor_id,), conn)
        if not tamanho or not cor:
            raise RegraDeNegocioError("Selecione o tamanho e a cor.")
        duplicada = fetch_one(
            "SELECT 1 FROM produto_variacoes "
            "WHERE produto_id = %s AND tamanho_id = %s AND cor_id = %s",
            (produto_id, tamanho_id, cor_id),
            conn,
        )
        if duplicada:
            raise RegraDeNegocioError("Esta combinação de tamanho e cor já existe no produto.")
        sku = f"{produto['codigo']}-{produto['id']:04d}-{tamanho['nome']}-{cor['codigo']}"
        variacao_id = fetch_one(
            "INSERT INTO produto_variacoes "
            "(produto_id, tamanho_id, cor_id, sku, preco_venda, estoque_minimo) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (produto_id, tamanho_id, cor_id, sku, preco, minimo),
            conn,
        )["id"]
    return {"id": variacao_id, "sku": sku}


def atualizar_variacao(variacao_id: int, preco_venda, estoque_minimo, ativo: bool) -> list[str]:
    """Atualiza preço, estoque mínimo e situação. Devolve alertas (não bloqueantes)."""
    preco = _preco(preco_venda, "preço de venda")
    minimo = _inteiro(estoque_minimo, "o estoque mínimo", 100000)
    with traduzir_erros_banco(), transaction() as conn:
        atual = fetch_one(
            "SELECT sku, custo_medio FROM produto_variacoes WHERE id = %s FOR UPDATE",
            (variacao_id,),
            conn,
        )
        if not atual:
            raise RegraDeNegocioError("Variação não encontrada.")
        execute(
            "UPDATE produto_variacoes SET preco_venda = %s, estoque_minimo = %s, ativo = %s "
            "WHERE id = %s",
            (preco, minimo, ativo, variacao_id),
            conn,
        )
    alertas = []
    if preco < atual["custo_medio"]:
        alertas.append(
            f"Atenção: o preço de venda ({fmt_brl(preco)}) de {atual['sku']} está abaixo "
            f"do custo médio ({fmt_brl(atual['custo_medio'])})."
        )
    return alertas
