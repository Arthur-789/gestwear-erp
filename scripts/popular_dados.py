"""Gera um histórico de demonstração (sempre o último ano) usando os próprios services do sistema.

Cada compra, venda, troca, pagamento e recebimento passa pelas mesmas regras e
transações do aplicativo, então estoque, financeiro e custos ficam consistentes.

Uso, na raiz do projeto e com o ambiente virtual ativo:

    python scripts/popular_dados.py
    python scripts/popular_dados.py --semente 7

O período é sempre o último ano: da data de hoje no ano anterior até hoje.
O volume é pequeno de propósito (cerca de 60 SKUs e algumas centenas de vendas): o
bastante para demonstrar todas as telas e análises, com povoamento rápido.

Requisitos: banco com schema e seed aplicados, ao menos um usuário ADMIN e
.streamlit/secrets.toml configurado. O script se recusa a rodar se já houver
vendas ou compras. Para recomeçar, apague os dados antes com scripts/limpar_dados.py.
A duração contra o Supabase depende da latência da conexão.
"""
import argparse
import logging
import math
import random
import sys
import time
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from db.connection import execute, fetch_all, fetch_one  # noqa: E402
from services import catalogo_service as catalogo  # noqa: E402
from services import clientes_service as clientes  # noqa: E402
from services import compras_service as compras  # noqa: E402
from services import contas_pagar_service as contas_pagar  # noqa: E402
from services import contas_receber_service as contas_receber  # noqa: E402
from services import estoque_service as estoque  # noqa: E402
from services import fornecedores_service as fornecedores  # noqa: E402
from services import operacional_service as operacional  # noqa: E402
from services import tesouraria_service as tesouraria  # noqa: E402
from services import usuarios_service as usuarios  # noqa: E402
from services import vendas_service as vendas  # noqa: E402
from services.excecoes import RegraDeNegocioError  # noqa: E402
from services.validadores import cnpj_valido, cpf_valido  # noqa: E402
from utils.datas import hoje, somar_meses  # noqa: E402

CENTAVO = Decimal("0.01")

SEMENTE_PADRAO = 100
MESES_DE_HISTORICO = 12

# ---------------------------------------------------------------- Catálogo
# (nome, categoria, preço, custo, tamanhos, cores, popularidade, fornecedor)
PRODUTOS = [
    ("Camiseta Básica Algodão", "Camisetas", 49.90, 19.0, ["P", "M", "G", "GG"], ["Branco", "Preto", "Azul Marinho"], 10, 0),
    ("Camiseta Oversized", "Camisetas", 79.90, 32.0, ["M", "G"], ["Preto", "Bege"], 5, 0),
    ("Camisa Linho", "Camisas", 149.90, 68.0, ["M", "G"], ["Bege", "Azul"], 3, 1),
    ("Calça Jeans Slim", "Calças", 179.90, 78.0, ["40", "42", "44"], ["Jeans Claro", "Jeans Escuro"], 9, 2),
    ("Calça Jogger", "Calças", 129.90, 54.0, ["P", "M", "G"], ["Preto", "Cinza"], 5, 2),
    ("Bermuda Tactel", "Bermudas e Shorts", 89.90, 36.0, ["M", "G"], ["Preto", "Azul Marinho"], 6, 1),
    ("Vestido Floral Midi", "Vestidos e Saias", 169.90, 71.0, ["P", "M", "G"], ["Rosa", "Verde"], 5, 1),
    ("Moletom Canguru", "Agasalhos", 159.90, 66.0, ["M", "G"], ["Cinza", "Preto"], 6, 3),
    ("Casaco Tricot", "Agasalhos", 189.90, 80.0, ["M", "G"], ["Bege", "Vermelho"], 2, 3),
    ("Kit 3 Meias Esportivas", "Íntimas e Meias", 39.90, 14.0, ["UN"], ["Branco", "Preto"], 8, 0),
    ("Cueca Boxer Algodão", "Íntimas e Meias", 34.90, 12.0, ["M", "G"], ["Preto", "Cinza"], 7, 0),
    ("Cinto Couro", "Acessórios", 79.90, 30.0, ["UN"], ["Preto", "Marrom"], 3, 3),
    ("Boné Aba Curva", "Acessórios", 59.90, 22.0, ["UN"], ["Preto", "Azul Marinho"], 4, 3),
]
# Tamanhos mais vendidos e SKUs encalhados (nunca vendem, viram estoque parado)
PESO_TAMANHO = {"PP": 0.4, "P": 0.9, "M": 1.5, "G": 1.4, "GG": 0.7, "38": 0.7, "40": 1.2, "42": 1.5,
                "44": 1.1, "46": 0.5, "UN": 1.0}
SKUS_ENCALHADOS = [("Casaco Tricot", "M", "Vermelho"), ("Camisa Linho", "G", "Azul"),
                   ("Calça Jogger", "G", "Cinza")]
# Produtos com índice de devolução acima da média, por motivo predominante
DEVOLUCAO_ALTA = {"Calça Jeans Slim": "TAMANHO_INADEQUADO", "Camisa Linho": "DEFEITO",
                  "Vestido Floral Midi": "ARREPENDIMENTO"}

FORNECEDORES = [
    # razão social, base do CNPJ, prazo de entrega (dias), parcelas, cidade
    ("Malharia Recife Ltda", "10234567", 3, 2, "Recife"),
    ("Confecções Boa Vista Ltda", "20345678", 5, 1, "Recife"),
    ("Jeans Nordeste Indústria Ltda", "30456789", 12, 2, "Toritama"),
    ("Tecelagem Agreste S.A.", "40567890", 7, 1, "Caruaru"),
]
PEDIDO_MINIMO = Decimal("300.00")

USUARIOS_DEMO = [
    ("ana.souza@gestwear.demo", "Ana Souza", "VENDEDOR", 0.40),
    ("bruno.lima@gestwear.demo", "Bruno Lima", "VENDEDOR", 0.35),
    ("carla.mendes@gestwear.demo", "Carla Mendes", "VENDEDOR", 0.25),
]
GERENTE_DEMO = ("diego.martins@gestwear.demo", "Diego Martins", "GERENTE")

NOMES = ["Maria", "Ana", "Juliana", "Fernanda", "Patrícia", "Camila", "Aline", "Larissa", "Beatriz", "Renata",
         "João", "Pedro", "Lucas", "Rafael", "Carlos", "Marcos", "Felipe", "Gabriel", "Rodrigo", "Thiago"]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Ferreira", "Almeida",
              "Ribeiro", "Carvalho", "Gomes", "Martins", "Araújo", "Barbosa", "Rocha", "Dias", "Nunes"]
CIDADES = ["Recife", "Olinda", "Jaboatão dos Guararapes", "Igarassu", "Paulista", "Camaragibe"]

# ---------------------------------------------------------------- Parâmetros da simulação
FATOR_SEMANA = {0: 0.85, 1: 0.80, 2: 0.90, 3: 1.00, 4: 1.25, 5: 1.60, 6: 0.55}  # segunda a domingo
FATOR_MES = {1: 0.85, 2: 0.80, 3: 0.90, 4: 0.95, 5: 1.20, 6: 0.95, 7: 1.00, 8: 0.95, 9: 0.95,
             10: 1.05, 11: 1.15, 12: 1.50}
# Peso extra por categoria em certos meses (agasalhos no inverno, leves no verão)
SAZONAL_CATEGORIA = {
    "Agasalhos": {6: 2.0, 7: 2.2, 8: 1.6, 12: 0.5, 1: 0.5, 2: 0.5},
    "Bermudas e Shorts": {11: 1.5, 12: 1.7, 1: 1.7, 2: 1.5, 7: 0.6},
    "Vestidos e Saias": {12: 1.8, 5: 1.6, 2: 1.3},
}
VENDAS_POR_DIA_BASE = 0.85
CRESCIMENTO_ANUAL = 0.25
CAPITAL_BANCO = Decimal("40000.00")
CAPITAL_CAIXA = Decimal("3000.00")


def _log(texto: str) -> None:
    print(texto, flush=True)


# ---------------------------------------------------------------- Utilitários
def tentar(funcao, *args, **kwargs):
    """Repete a chamada em caso de falha transitória de conexão (regras de negócio não repetem)."""
    for tentativa in range(4):
        try:
            return funcao(*args, **kwargs)
        except psycopg.OperationalError:
            if tentativa == 3:
                raise
            time.sleep(2 * (tentativa + 1))


def _dinheiro(valor: float | Decimal) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def _digito(numeros: list[int], pesos: list[int]) -> int:
    resto = sum(n * p for n, p in zip(numeros, pesos)) % 11
    return 0 if resto < 2 else 11 - resto


def gerar_cpf(rng: random.Random) -> str:
    base = [rng.randint(0, 9) for _ in range(9)]
    base.append(sum(n * p for n, p in zip(base, range(10, 1, -1))) * 10 % 11 % 10)
    base.append(sum(n * p for n, p in zip(base, range(11, 1, -1))) * 10 % 11 % 10)
    cpf = "".join(map(str, base))
    return cpf if cpf_valido(cpf) else gerar_cpf(rng)


def gerar_cnpj(base8: str) -> str:
    base = [int(c) for c in base8] + [0, 0, 0, 1]
    base.append(_digito(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    base.append(_digito(base, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    cnpj = "".join(map(str, base))
    assert cnpj_valido(cnpj), cnpj
    return cnpj


def poisson(rng: random.Random, media: float) -> int:
    limite, k, p = math.exp(-media), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def escolher(rng: random.Random, opcoes: list, pesos: list):
    return rng.choices(opcoes, weights=pesos, k=1)[0]


def ultima_sexta_de_novembro(ano: int) -> date:
    dia = date(ano, 11, 30)
    while dia.weekday() != 4:
        dia -= timedelta(days=1)
    return dia


# ---------------------------------------------------------------- Cadastros
class Cenario:
    """Dados de cadastro criados e o estado da simulação."""

    def __init__(self, rng: random.Random, inicio: date, fim: date):
        self.rng, self.inicio, self.fim = rng, inicio, fim
        self.total_dias = max((fim - inicio).days, 1)
        self.admin_id = 0
        self.vendedores: list[tuple[int, float]] = []
        self.gerente_id = 0
        self.fornecedores: list[dict] = []
        self.skus: dict[int, dict] = {}
        self.clientes: list[dict] = []
        self.conta_caixa = self.conta_banco = 0
        self.pendentes: dict[int, int] = {}          # variacao_id -> quantidade em pedidos abertos
        self.itens_pedido: dict[int, dict[int, int]] = {}  # compra_id -> {variacao_id: quantidade}
        self.recebimentos: dict[date, list[int]] = {}  # data -> compras a receber
        self.devolucoes: dict[date, list[dict]] = {}   # data -> devoluções agendadas
        self.contagem = {"vendas": 0, "compras": 0, "trocas": 0, "devolucoes": 0, "falhas": 0}
        self.mensagens_falha: list[str] = []

    def falha(self, contexto: str, erro: Exception) -> None:
        self.contagem["falhas"] += 1
        if len(self.mensagens_falha) < 8:
            self.mensagens_falha.append(f"{contexto}: {erro}")


def criar_usuarios(c: Cenario) -> None:
    admin = fetch_one("SELECT id FROM usuarios WHERE perfil = 'ADMIN' AND ativo ORDER BY id LIMIT 1")
    if not admin:
        raise SystemExit("Nenhum usuário ADMIN ativo encontrado. Cadastre o administrador antes (README).")
    c.admin_id = admin["id"]
    for email, nome, perfil, peso in USUARIOS_DEMO:
        existente = usuarios.buscar_por_email(email)
        c.vendedores.append((existente["id"] if existente else usuarios.criar_usuario(email, nome, perfil), peso))
    email, nome, perfil = GERENTE_DEMO
    existente = usuarios.buscar_por_email(email)
    c.gerente_id = existente["id"] if existente else usuarios.criar_usuario(email, nome, perfil)


def criar_contas(c: Cenario) -> None:
    contas = {conta["tipo"]: conta for conta in tesouraria.listar_contas()}
    c.conta_caixa, c.conta_banco = contas["CAIXA"]["id"], contas["BANCO"]["id"]
    for tipo, capital in (("CAIXA", CAPITAL_CAIXA), ("BANCO", CAPITAL_BANCO)):
        conta = contas[tipo]
        if conta["movimentos"] == 0:
            tesouraria.atualizar_conta(conta["id"], conta["nome"], conta["ativa"], capital)


def criar_fornecedores(c: Cenario) -> None:
    for razao, base, prazo, parcelas, cidade in FORNECEDORES:
        cnpj = gerar_cnpj(base)
        email = razao.split()[0].lower().replace("ç", "c").replace("õ", "o") + "@exemplo.com.br"
        fornecedor_id = fornecedores.criar_fornecedor(razao, cnpj, "Setor Comercial", "8130000000", email, cidade, "PE")
        c.fornecedores.append({"id": fornecedor_id, "prazo": prazo, "parcelas": parcelas, "skus": []})


def criar_catalogo(c: Cenario) -> None:
    categorias = {x["nome"]: x["id"] for x in catalogo.listar_categorias()}
    tamanhos = {x["nome"]: x["id"] for x in catalogo.listar_tamanhos()}
    cores = {x["nome"]: x["id"] for x in catalogo.listar_cores()}
    encalhados = set(SKUS_ENCALHADOS)
    for nome, categoria, preco, custo, tams, cors, popularidade, indice_fornecedor in PRODUTOS:
        produto_id = catalogo.criar_produto(nome, f"{nome} (dados de demonstração)", categorias[categoria])
        for tam in tams:
            for cor in cors:
                peso = popularidade * PESO_TAMANHO[tam] * c.rng.uniform(0.6, 1.4)
                if (nome, tam, cor) in encalhados:
                    peso = 0.0
                variacao = catalogo.criar_variacao(produto_id, tamanhos[tam], cores[cor], _dinheiro(preco), 2)
                c.skus[variacao["id"]] = {
                    "id": variacao["id"], "produto": nome, "categoria": categoria, "tamanho": tam, "cor": cor,
                    "preco": _dinheiro(preco), "custo_base": custo, "peso": peso,
                    "fornecedor": c.fornecedores[indice_fornecedor], "minimo": 2, "alvo": 6, "ponto": 3,
                }
                c.fornecedores[indice_fornecedor]["skus"].append(variacao["id"])
    # Parâmetros de reposição proporcionais à participação de cada SKU nas vendas
    total = sum(s["peso"] for s in c.skus.values())
    for sku in c.skus.values():
        participacao = sku["peso"] / total
        sku["minimo"] = max(2, math.ceil(participacao * 30))
        sku["ponto"] = sku["minimo"] + max(1, math.ceil(participacao * 45))
        sku["alvo"] = sku["minimo"] + max(4, math.ceil(participacao * 120))
        if sku["peso"] == 0:
            sku["alvo"], sku["ponto"] = 5, 0
        execute("UPDATE produto_variacoes SET estoque_minimo = %s WHERE id = %s", (sku["minimo"], sku["id"]))


def criar_clientes(c: Cenario, quantidade: int = 40) -> None:
    usados = set()
    for _ in range(quantidade):
        cpf = gerar_cpf(c.rng)
        if cpf in usados:
            continue
        usados.add(cpf)
        nome = f"{c.rng.choice(NOMES)} {c.rng.choice(SOBRENOMES)} {c.rng.choice(SOBRENOMES)}"
        cidade = escolher(c.rng, CIDADES, [5, 3, 3, 2, 2, 1])
        telefone = f"819{c.rng.randint(80000000, 99999999)}"
        email = f"{nome.split()[0].lower()}.{c.rng.randint(100, 999)}@exemplo.com".replace("á", "a")
        cliente_id = clientes.criar_cliente(nome, cpf, telefone, email, cidade, "PE")
        c.clientes.append({"id": cliente_id, "peso": c.rng.lognormvariate(0, 0.9), "perfil": "normal"})
    # Garante parcelas vencidas para demonstrar a inadimplência: entre os clientes que mais compram,
    # 2 nunca pagam e 5 pagam com muito atraso
    frequentes = sorted(c.clientes, key=lambda x: x["peso"], reverse=True)
    for cliente in c.rng.sample(frequentes[:10], 2):
        cliente["perfil"] = "inadimplente"
    for cliente in c.rng.sample([x for x in frequentes[:20] if x["perfil"] == "normal"], 5):
        cliente["perfil"] = "lento"


# ---------------------------------------------------------------- Compras
def _custo_do_dia(c: Cenario, sku: dict, dia: date) -> Decimal:
    progresso = (dia - c.inicio).days / c.total_dias
    return _dinheiro(sku["custo_base"] * (1 + 0.04 * progresso) * c.rng.uniform(0.97, 1.03))


def _fazer_pedido(c: Cenario, fornecedor: dict, itens: dict[int, int], dia: date) -> None:
    linhas = [{"variacao_id": v, "quantidade": q, "custo_unitario": _custo_do_dia(c, c.skus[v], dia)}
              for v, q in itens.items()]
    try:
        compra_id = tentar(compras.criar_pedido, fornecedor["id"], dia, fornecedor["parcelas"],
                           dia + timedelta(days=30), None, linhas, c.admin_id)
    except RegraDeNegocioError as erro:
        c.falha(f"pedido de {dia}", erro)
        return
    for variacao_id, quantidade in itens.items():
        c.pendentes[variacao_id] = c.pendentes.get(variacao_id, 0) + quantidade
    c.recebimentos.setdefault(dia + timedelta(days=fornecedor["prazo"]), []).append(compra_id)
    c.contagem["compras"] += 1
    c.itens_pedido[compra_id] = itens


def pedido_de_abertura(c: Cenario) -> None:
    for fornecedor in c.fornecedores:
        itens = {v: c.skus[v]["alvo"] for v in fornecedor["skus"]}
        _fazer_pedido(c, fornecedor, itens, c.inicio)


def reposicao_semanal(c: Cenario, dia: date, saldos: dict[int, int]) -> None:
    for fornecedor in c.fornecedores:
        itens, total = {}, Decimal("0.00")
        for variacao_id in fornecedor["skus"]:
            sku = c.skus[variacao_id]
            disponivel = saldos[variacao_id] + c.pendentes.get(variacao_id, 0)
            if sku["peso"] > 0 and disponivel <= sku["ponto"]:
                quantidade = sku["alvo"] - disponivel
                if quantidade > 0:
                    itens[variacao_id] = quantidade
                    total += quantidade * _dinheiro(sku["custo_base"])
        if itens and total >= PEDIDO_MINIMO:
            _fazer_pedido(c, fornecedor, itens, dia)


def receber_compras(c: Cenario, dia: date) -> None:
    for compra_id in c.recebimentos.pop(dia, []):
        try:
            tentar(compras.receber_compra, compra_id, dia, c.admin_id)
        except RegraDeNegocioError as erro:
            c.falha(f"recebimento da compra {compra_id}", erro)
        for variacao_id, quantidade in c.itens_pedido.pop(compra_id, {}).items():
            c.pendentes[variacao_id] = max(0, c.pendentes.get(variacao_id, 0) - quantidade)


# ---------------------------------------------------------------- Vendas
def fator_do_dia(c: Cenario, dia: date) -> float:
    fator = FATOR_SEMANA[dia.weekday()] * FATOR_MES[dia.month]
    fator *= 1 + CRESCIMENTO_ANUAL * (dia - c.inicio).days / c.total_dias
    black = ultima_sexta_de_novembro(dia.year)
    if dia == black:
        fator *= 2.4
    elif black < dia <= black + timedelta(days=2):
        fator *= 1.4
    return fator


def _peso_sku(sku: dict, dia: date) -> float:
    return sku["peso"] * SAZONAL_CATEGORIA.get(sku["categoria"], {}).get(dia.month, 1.0)


def _forma_pagamento(c: Cenario, cliente: dict | None, total: Decimal) -> tuple[str, int]:
    if cliente is None:
        forma = escolher(c.rng, ["PIX", "DEBITO", "DINHEIRO", "CREDITO"], [40, 25, 20, 15])
    else:
        forma = escolher(c.rng, ["PIX", "CREDITO", "DEBITO", "DINHEIRO"], [30, 40, 20, 10])
    if forma != "CREDITO":
        return forma, 1
    parcelas = 1
    if cliente is not None:
        parcelas = escolher(c.rng, [1, 2, 3, 6], [40, 25, 25, 10])
        while parcelas > 1 and total / parcelas < 30:
            parcelas -= 1
    return forma, parcelas


def vender(c: Cenario, dia: date, saldos: dict[int, int]) -> None:
    rng = c.rng
    disponiveis = [s for s in c.skus.values() if saldos[s["id"]] > 0 and s["peso"] > 0]
    if not disponiveis:
        return
    cliente = escolher(rng, c.clientes, [x["peso"] for x in c.clientes]) if rng.random() < 0.6 else None
    vendedor_id, _ = escolher(rng, c.vendedores, [peso for _, peso in c.vendedores])
    linhas = escolher(rng, [1, 2, 3, 4], [25, 35, 25, 15])
    itens, escolhidos = [], set()
    for _ in range(linhas):
        candidatos = [s for s in disponiveis if s["id"] not in escolhidos]
        if not candidatos:
            break
        sku = escolher(rng, candidatos, [_peso_sku(s, dia) or 0.001 for s in candidatos])
        quantidade = min(escolher(rng, [1, 2, 3], [85, 12, 3]), saldos[sku["id"]])
        escolhidos.add(sku["id"])
        itens.append({"variacao_id": sku["id"], "quantidade": quantidade})
    subtotal = sum(c.skus[i["variacao_id"]]["preco"] * i["quantidade"] for i in itens)

    black = dia == ultima_sexta_de_novembro(dia.year)
    prob_desconto = 0.7 if black else (0.30 if vendedor_id == c.vendedores[1][0] else 0.15)
    desconto, operador = Decimal("0.00"), vendedor_id
    if rng.random() < prob_desconto:
        percentual = escolher(rng, [5, 10, 15, 20], [40, 35, 15, 10] if not black else [10, 25, 35, 30])
        desconto = (subtotal * percentual / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if percentual > 10:
            operador = c.gerente_id  # desconto acima de 10% exige gerência
    forma, parcelas = _forma_pagamento(c, cliente, subtotal - desconto)
    try:
        venda = tentar(vendas.criar_venda, cliente["id"] if cliente else None, dia, desconto, forma,
                       parcelas, None, itens, operador)
    except RegraDeNegocioError as erro:
        c.falha(f"venda de {dia}", erro)
        return
    c.contagem["vendas"] += 1
    for item in itens:
        saldos[item["variacao_id"]] -= item["quantidade"]
    agendar_devolucao(c, dia, venda["id"], itens, operador)


def agendar_devolucao(c: Cenario, dia: date, venda_id: int, itens: list[dict], operador: int) -> None:
    rng = c.rng
    item = rng.choice(itens)
    sku = c.skus[item["variacao_id"]]
    probabilidade = 0.055 * (2.8 if sku["produto"] in DEVOLUCAO_ALTA else 1.0)
    if rng.random() >= probabilidade:
        return
    espera = int(rng.triangular(1, 25, 5))
    data = dia + timedelta(days=espera)
    if data > c.fim:
        return
    motivo_alto = DEVOLUCAO_ALTA.get(sku["produto"])
    if motivo_alto and rng.random() < 0.6:
        motivo = motivo_alto
    else:
        motivo = escolher(rng, ["TAMANHO_INADEQUADO", "ARREPENDIMENTO", "DEFEITO", "OUTRO"], [38, 27, 15, 20])
    c.devolucoes.setdefault(data, []).append({
        "venda_id": venda_id, "variacao_id": item["variacao_id"], "motivo": motivo,
        "quantidade": rng.randint(1, item["quantidade"]), "operador": operador,
        "troca": rng.random() < 0.40,
    })


def processar_devolucoes(c: Cenario, dia: date, saldos: dict[int, int]) -> None:
    rng = c.rng
    for pedido in c.devolucoes.pop(dia, []):
        item_venda = fetch_one("SELECT id FROM itens_venda WHERE venda_id = %s AND variacao_id = %s",
                               (pedido["venda_id"], pedido["variacao_id"]))
        devolvidos = [{"item_venda_id": item_venda["id"], "quantidade": pedido["quantidade"]}]
        tipo, novos, forma = "DEVOLUCAO", [], None
        if pedido["troca"]:
            original = c.skus[pedido["variacao_id"]]
            mesmos = [s for s in c.skus.values() if s["produto"] == original["produto"]
                      and s["id"] != original["id"] and saldos[s["id"]] >= pedido["quantidade"] and s["peso"] > 0]
            if mesmos:
                novo = rng.choice(mesmos)
                tipo = "TROCA"
                novos = [{"variacao_id": novo["id"], "quantidade": pedido["quantidade"]}]
                forma = escolher(rng, ["DINHEIRO", "PIX", "DEBITO"], [40, 40, 20])
        try:
            tentar(operacional.registrar, pedido["venda_id"], tipo, pedido["motivo"], dia,
                               forma if tipo == "TROCA" else None, None, devolvidos, novos, pedido["operador"])
        except RegraDeNegocioError as erro:
            c.falha(f"devolução da venda {pedido['venda_id']}", erro)
            continue
        c.contagem["trocas" if tipo == "TROCA" else "devolucoes"] += 1
        if pedido["motivo"] != "DEFEITO":
            saldos[pedido["variacao_id"]] += pedido["quantidade"]
        if novos:
            saldos[novos[0]["variacao_id"]] -= novos[0]["quantidade"]


# ---------------------------------------------------------------- Financeiro
def lancar_despesas(c: Cenario, dia: date, categorias: dict[str, int]) -> None:
    rng = c.rng
    fixas = {
        5: ("Aluguel da loja", "Aluguel", 1000, 0),
        10: ("Folha de pagamento", "Salários e Encargos", 1600, 0),
        15: ("Conta de energia e água", "Energia e Água", 200, 0.18),
        20: ("Campanha de marketing digital", "Marketing", 220, 0.35),
        25: ("Impostos e taxas do mês", "Impostos e Taxas", 280, 0.25),
    }
    if dia.day not in fixas:
        return
    descricao, categoria, valor, variacao = fixas[dia.day]
    valor = _dinheiro(valor * (1 + rng.uniform(-variacao, variacao)))
    mes = f"{dia.month:02d}/{dia.year}"
    try:
        tentar(contas_pagar.criar_despesa, f"{descricao} {mes}", categorias[categoria], None, valor, 1, dia)
    except RegraDeNegocioError as erro:
        c.falha(f"despesa de {dia}", erro)
    if dia.day == 25 and rng.random() < 0.4:
        try:
            tentar(contas_pagar.criar_despesa, f"Manutenção e pequenos reparos {mes}", categorias["Outras Despesas"],
                   None, _dinheiro(rng.uniform(80, 250)), 1, dia)
        except RegraDeNegocioError as erro:
            c.falha(f"despesa de {dia}", erro)


def _tolerancia_dias_uteis(dia: date) -> int:
    """Na segunda-feira, vencimentos de sábado e domingo ainda contam como em dia."""
    return 2 if dia.weekday() == 0 else 0


def pagar_contas(c: Cenario, dia: date, obter_saldo_caixa) -> None:
    if dia.weekday() >= 5:
        return
    rng = c.rng
    abertas = fetch_all(
        "SELECT id, valor, data_vencimento, troca_devolucao_id FROM contas_pagar "
        "WHERE status = 'ABERTA' AND data_vencimento <= %s ORDER BY data_vencimento, id", (dia,))
    saldo_caixa = None
    for conta in abertas:
        atraso = (dia - conta["data_vencimento"]).days
        em_dia = atraso <= _tolerancia_dias_uteis(dia)
        if not (em_dia and rng.random() < 0.75 or not em_dia and (rng.random() < 0.25 or atraso >= 12)):
            continue
        usar_caixa = False
        if conta["troca_devolucao_id"] is not None:  # estornos a clientes saem do caixa, quando houver saldo
            saldo_caixa = obter_saldo_caixa() if saldo_caixa is None else saldo_caixa
            usar_caixa = conta["valor"] <= saldo_caixa
        conta_id = c.conta_caixa if usar_caixa else c.conta_banco
        try:
            tentar(contas_pagar.pagar, conta["id"], conta_id, dia, c.admin_id)
            if usar_caixa:
                saldo_caixa -= conta["valor"]
        except RegraDeNegocioError as erro:
            c.falha(f"pagamento da conta {conta['id']}", erro)


def receber_parcelas(c: Cenario, dia: date) -> None:
    if dia.weekday() >= 5:
        return
    rng = c.rng
    perfis = {x["id"]: x["perfil"] for x in c.clientes}
    abertas = fetch_all(
        "SELECT id, cliente_id, data_vencimento FROM contas_receber "
        "WHERE status = 'ABERTA' AND data_vencimento <= %s ORDER BY data_vencimento, id", (dia,))
    for conta in abertas:
        atraso = (dia - conta["data_vencimento"]).days
        em_dia = atraso <= _tolerancia_dias_uteis(dia)
        perfil = perfis.get(conta["cliente_id"], "normal")
        if perfil == "inadimplente":
            paga = False
        elif perfil == "lento":
            paga = rng.random() < 0.01
        else:
            paga = em_dia and rng.random() < 0.70 or not em_dia and rng.random() < 0.15
        if not paga:
            continue
        try:
            tentar(contas_receber.receber, conta["id"], c.conta_banco, dia, c.admin_id)
        except RegraDeNegocioError as erro:
            c.falha(f"recebimento da conta {conta['id']}", erro)


def conciliar_meses_antigos(c: Cenario) -> int:
    """Concilia as movimentações até o fechamento de cada mês concluído há mais de 10 dias."""
    total, referencia = 0, c.inicio.replace(day=1)
    while True:
        fechamento = somar_meses(referencia, 1) - timedelta(days=1)
        data_conciliacao = fechamento + timedelta(days=5)
        if data_conciliacao > c.fim - timedelta(days=10):
            break
        ids = [m["id"] for m in fetch_all(
            "SELECT id FROM movimentacoes_financeiras WHERE NOT conciliado "
            "AND (data_movimento AT TIME ZONE 'America/Recife')::date <= %s", (fechamento,))]
        if ids:
            total += tentar(tesouraria.conciliar, ids, data_conciliacao)
        referencia = somar_meses(referencia, 1)
    return total


def ajustar_inventario(c: Cenario, quantidade_skus: int = 4) -> None:
    """Contagem final: pequenas divergências de inventário em alguns SKUs."""
    for sku in c.rng.sample([s for s in c.skus.values() if s["peso"] > 0], quantidade_skus):
        saldo = fetch_one("SELECT estoque_atual FROM produto_variacoes WHERE id = %s", (sku["id"],))["estoque_atual"]
        contado = max(0, saldo + c.rng.choice([-2, -1, -1, 1]))
        if contado != saldo:
            try:
                tentar(estoque.ajustar_estoque, sku["id"], contado, "Contagem de inventário", c.admin_id)
            except RegraDeNegocioError as erro:
                c.falha(f"ajuste de {sku['id']}", erro)


# ---------------------------------------------------------------- Simulação
def banco_ja_tem_movimento() -> bool:
    return bool(fetch_one("SELECT (SELECT count(*) FROM vendas) + (SELECT count(*) FROM compras) AS n")["n"])


def executar(semente: int = SEMENTE_PADRAO) -> dict:
    """Gera o histórico do último ano: da data de hoje no ano anterior até hoje."""
    if banco_ja_tem_movimento():
        raise SystemExit("O banco já possui vendas ou compras. Para gerar um novo histórico, apague os dados antes: "
                         "python scripts/limpar_dados.py")
    fim = hoje()
    inicio = somar_meses(fim, -MESES_DE_HISTORICO)
    rng = random.Random(semente)
    c = Cenario(rng, inicio, fim)
    inicio_execucao = time.time()

    _log(f"Gerando histórico de {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} (semente {semente})...")
    criar_usuarios(c)
    criar_contas(c)
    criar_fornecedores(c)
    criar_catalogo(c)
    criar_clientes(c)
    categorias = {x["nome"]: x["id"] for x in fetch_all("SELECT id, nome FROM categorias_financeiras")}
    _log(f"Cadastros prontos: {len(c.skus)} SKUs, {len(c.clientes)} clientes, {len(c.fornecedores)} fornecedores.")

    pedido_de_abertura(c)
    dia, mes_atual = inicio, None
    while dia <= fim:
        if dia.month != mes_atual:
            mes_atual = dia.month
            _log(f"  {dia:%m/%Y}: vendas {c.contagem['vendas']}, compras {c.contagem['compras']}, "
                 f"trocas e devoluções {c.contagem['trocas'] + c.contagem['devolucoes']} "
                 f"({time.time() - inicio_execucao:.0f}s)")
        receber_compras(c, dia)
        vendas_do_dia = poisson(rng, VENDAS_POR_DIA_BASE * fator_do_dia(c, dia))
        segunda_de_reposicao = dia.weekday() == 0 and dia != inicio
        saldos = None
        if vendas_do_dia or segunda_de_reposicao or dia in c.devolucoes:
            saldos = {x["id"]: x["estoque_atual"]
                      for x in fetch_all("SELECT id, estoque_atual FROM produto_variacoes")}
        if segunda_de_reposicao:
            reposicao_semanal(c, dia, saldos)
        for _ in range(vendas_do_dia):
            vender(c, dia, saldos)
        if dia in c.devolucoes:
            processar_devolucoes(c, dia, saldos)
        lancar_despesas(c, dia, categorias)
        pagar_contas(c, dia, lambda: next(
            x["saldo_atual"] for x in tesouraria.listar_contas() if x["id"] == c.conta_caixa))
        receber_parcelas(c, dia)
        dia += timedelta(days=1)

    ajustar_inventario(c)
    conciliadas = conciliar_meses_antigos(c)
    return resumo_final(c, conciliadas, time.time() - inicio_execucao)


def resumo_final(c: Cenario, conciliadas: int, segundos: float) -> dict:
    vendas_totais = fetch_one("SELECT count(*) AS n, COALESCE(SUM(valor_total), 0) AS valor FROM vendas")
    saldos = {x["nome"]: x["saldo_atual"] for x in tesouraria.listar_contas()}
    abertas = fetch_one("SELECT (SELECT count(*) FROM contas_receber WHERE status = 'ABERTA') AS receber, "
                        "(SELECT count(*) FROM contas_pagar WHERE status = 'ABERTA') AS pagar")
    zerados = fetch_one("SELECT count(*) AS n FROM produto_variacoes WHERE estoque_atual = 0")["n"]
    resumo = {
        "vendas": vendas_totais["n"], "faturamento": vendas_totais["valor"], **c.contagem,
        "saldos": saldos, "contas_receber_abertas": abertas["receber"], "contas_pagar_abertas": abertas["pagar"],
        "skus_zerados": zerados, "movimentacoes_conciliadas": conciliadas, "segundos": segundos,
    }
    _log("\nConcluído.")
    _log(f"  Vendas: {resumo['vendas']} (faturamento R$ {resumo['faturamento']:,.2f})")
    _log(f"  Compras: {c.contagem['compras']} | Trocas: {c.contagem['trocas']} | Devoluções: {c.contagem['devolucoes']}")
    _log("  Saldos: " + " | ".join(f"{nome}: R$ {valor:,.2f}" for nome, valor in saldos.items()))
    _log(f"  Contas abertas: {abertas['receber']} a receber, {abertas['pagar']} a pagar | SKUs zerados: {zerados}")
    _log(f"  Movimentações conciliadas: {conciliadas} | Tempo: {segundos / 60:.1f} min")
    if c.contagem["falhas"]:
        _log(f"  Atenção: {c.contagem['falhas']} operações foram recusadas pelas regras. Exemplos:")
        for mensagem in c.mensagens_falha:
            _log(f"    - {mensagem}")
    return resumo


def main(argv: list[str] | None = None) -> None:
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(
        description="Gera o histórico de demonstração do último ano (da data de hoje no ano anterior até hoje)."
    )
    parser.add_argument("--semente", type=int, default=SEMENTE_PADRAO,
                        help=f"semente aleatória, para repetir o mesmo histórico (padrão: {SEMENTE_PADRAO})")
    args = parser.parse_args(argv)
    executar(args.semente)


if __name__ == "__main__":
    main()
