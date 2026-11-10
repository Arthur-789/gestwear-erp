"""Validações e normalizações reutilizadas pelos serviços."""
import re

from config import UFS
from services.excecoes import RegraDeNegocioError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def somente_digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


def texto_opcional(texto: str | None) -> str | None:
    """Remove espaços extras e devolve None para texto vazio."""
    limpo = " ".join((texto or "").split())
    return limpo or None


def escapar_like(texto: str) -> str:
    """Escapa curingas para uso em ILIKE."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def email_valido(email: str) -> bool:
    return bool(_EMAIL_RE.match(email or ""))


def cpf_valido(cpf: str) -> bool:
    d = somente_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d[i]) * (tamanho + 1 - i) for i in range(tamanho))
        if (soma * 10 % 11) % 10 != int(d[tamanho]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    d = somente_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6] + pesos_1
    for pesos, posicao in ((pesos_1, 12), (pesos_2, 13)):
        resto = sum(int(d[i]) * pesos[i] for i in range(posicao)) % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(d[posicao]):
            return False
    return True


def normalizar_contato(
    telefone: str | None, email: str | None, uf: str | None
) -> tuple[str | None, str | None, str | None]:
    """Valida e padroniza telefone (só dígitos), e-mail (minúsculo) e UF (maiúscula)."""
    tel = somente_digitos(telefone) or None
    if tel and len(tel) not in (10, 11):
        raise RegraDeNegocioError("Telefone inválido. Informe o DDD e o número.")
    mail = (email or "").strip().lower() or None
    if mail and not email_valido(mail):
        raise RegraDeNegocioError("E-mail inválido.")
    sigla = (uf or "").strip().upper() or None
    if sigla and sigla not in UFS:
        raise RegraDeNegocioError("UF inválida.")
    return tel, mail, sigla
