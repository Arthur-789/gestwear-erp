"""Apaga os dados do sistema e devolve o banco ao estado de logo após o seed inicial.

USO MANUAL, SOMENTE QUANDO NECESSÁRIO. Nada no aplicativo chama este script.
A operação não pode ser desfeita.

    python scripts/limpar_dados.py

O que é apagado: produtos e variações, clientes, fornecedores, compras, vendas,
trocas e devoluções, movimentações de estoque, contas a pagar e a receber e
movimentações financeiras. Os identificadores voltam a começar em 1.

O que é mantido: usuários (exceto os de demonstração @gestwear.demo, que não
sejam administradores), categorias, tamanhos, cores, categorias financeiras e as
contas financeiras (com o saldo inicial zerado).

Antes de apagar, o script mostra o banco de destino e a quantidade de registros, e
só prossegue se a frase de confirmação for digitada exatamente. Tudo é feito em uma
única transação: se algo falhar, nada é apagado.

Para gerar novamente o histórico de demonstração depois da limpeza:

    python scripts/popular_dados.py
"""
import logging
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from db.connection import execute, fetch_one, transaction  # noqa: E402

FRASE_CONFIRMACAO = "APAGAR TUDO"
DOMINIO_DEMONSTRACAO = "%@gestwear.demo"

# Todas as tabelas de dados, apagadas na mesma instrução (a ordem não importa)
TABELAS = (
    "movimentacoes_financeiras",
    "contas_pagar",
    "contas_receber",
    "itens_novos_troca",
    "itens_devolvidos",
    "trocas_devolucoes",
    "movimentacoes_estoque",
    "itens_venda",
    "vendas",
    "itens_compra",
    "compras",
    "produto_variacoes",
    "produtos",
    "clientes",
    "fornecedores",
)
# Tabelas de configuração que permanecem
MANTIDAS = ("categorias", "tamanhos", "cores", "categorias_financeiras", "contas_financeiras", "usuarios")


def _banco_de_destino() -> str:
    """Servidor e banco configurados no secrets.toml, sem usuário nem senha."""
    try:
        url = urlparse(st.secrets["database"]["url"])
    except Exception:
        raise SystemExit("Segredo [database] url não configurado em .streamlit/secrets.toml.")
    servidor = url.hostname or parse_qs(url.query).get("host", ["local"])[0]
    porta = f":{url.port}" if url.port else ""
    return f"{servidor}{porta}/{url.path.lstrip('/')}"


def _contar(tabela: str) -> int:
    return fetch_one(f"SELECT count(*) AS n FROM {tabela}")["n"]


def _usuarios_de_demonstracao() -> int:
    return fetch_one(
        "SELECT count(*) AS n FROM usuarios WHERE email ILIKE %s AND perfil <> 'ADMIN'",
        (DOMINIO_DEMONSTRACAO,),
    )["n"]


def main() -> None:
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    destino = _banco_de_destino()
    contagens = {tabela: _contar(tabela) for tabela in TABELAS}
    demonstracao = _usuarios_de_demonstracao()

    print(f"Banco de destino: {destino}\n")
    if not any(contagens.values()) and not demonstracao:
        print("Não há dados para apagar. Nada foi alterado.")
        return

    print("Registros que serão apagados:")
    for tabela, quantidade in contagens.items():
        print(f"  {tabela:<28}{quantidade:>8}")
    print(f"  {'usuários de demonstração':<28}{demonstracao:>8}")
    print(f"\nSerão mantidos: {', '.join(MANTIDAS)} (contas financeiras com saldo inicial zerado).")
    if "supabase" in destino.lower():
        print("\nATENÇÃO: este é o banco do Supabase (o mesmo usado pelo sistema publicado).")
    print("Esta operação NÃO pode ser desfeita.\n")

    try:
        resposta = input(f'Para confirmar, digite exatamente "{FRASE_CONFIRMACAO}": ')
    except EOFError:
        resposta = ""
    if resposta.strip() != FRASE_CONFIRMACAO:
        print("Confirmação não recebida. Nada foi apagado.")
        raise SystemExit(1)

    with transaction() as conn:
        execute("TRUNCATE " + ", ".join(TABELAS) + " RESTART IDENTITY", None, conn)
        execute(
            "DELETE FROM usuarios WHERE email ILIKE %s AND perfil <> 'ADMIN'", (DOMINIO_DEMONSTRACAO,), conn
        )
        execute("UPDATE contas_financeiras SET saldo_inicial = 0", None, conn)

    restantes = sum(_contar(tabela) for tabela in TABELAS)
    if restantes:
        raise SystemExit(f"Falha inesperada: restaram {restantes} registros.")
    print("\nConcluído. Os dados foram apagados e o banco voltou ao estado inicial.")
    print("Se o aplicativo estiver aberto, atualize a página (os painéis guardam dados por até 2 minutos).")


if __name__ == "__main__":
    main()
