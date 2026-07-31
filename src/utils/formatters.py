"""Funcoes de apoio para formatar telefones, datas e textos longos."""

import re
import unicodedata
from datetime import datetime, timezone, timedelta

# Fuso de Brasilia (sem horario de verao).
BRT = timezone(timedelta(hours=-3))

DIAS_SEMANA = [
    "segunda-feira", "terca-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sabado", "domingo",
]

# Limite pratico de caracteres por mensagem no WhatsApp.
LIMITE_WHATSAPP = 4096


def so_digitos(valor: str) -> str:
    """Remove tudo que nao for digito."""
    return re.sub(r"\D", "", valor or "")


def normalizar_telefone(numero: str) -> str:
    """Normaliza um telefone brasileiro para o formato E.164 sem '+'.

    >>> normalizar_telefone("(11) 98888-7777")
    '5511988887777'
    """
    d = so_digitos(numero)
    if not d:
        return ""
    if d.startswith("55") and len(d) >= 12:
        return d
    if len(d) in (10, 11):
        return "55" + d
    return d


def para_jid(numero: str) -> str:
    """Converte um telefone em JID do WhatsApp (ex: 5511988887777@s.whatsapp.net)."""
    if "@" in (numero or ""):
        return numero
    return f"{normalizar_telefone(numero)}@s.whatsapp.net"


def do_jid(jid: str) -> str:
    """Extrai apenas o numero de um JID."""
    return so_digitos((jid or "").split("@")[0])


def formatar_telefone_br(numero: str) -> str:
    """Formata para exibicao: (11) 98888-7777."""
    d = so_digitos(numero)
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return numero


def agora_brt() -> datetime:
    """Data/hora atual no fuso de Brasilia."""
    return datetime.now(BRT)


def formatar_data(dt: datetime | None = None, com_hora: bool = False) -> str:
    """Formata uma data como dd/mm/aaaa (opcionalmente com hh:mm)."""
    dt = dt or agora_brt()
    return dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def dia_da_semana(dt: datetime | None = None) -> str:
    """Nome do dia da semana em portugues."""
    dt = dt or agora_brt()
    return DIAS_SEMANA[dt.weekday()]


def saudacao(dt: datetime | None = None) -> str:
    """Bom dia / Boa tarde / Boa noite conforme a hora."""
    hora = (dt or agora_brt()).hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


def normalizar_texto(texto: str) -> str:
    """Minusculo, sem acentos e sem espacos nas pontas. Util para comparar entradas."""
    texto = (texto or "").strip().lower()
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def dividir_texto(texto: str, limite: int = LIMITE_WHATSAPP) -> list[str]:
    """Quebra um texto longo em varias mensagens respeitando quebras de linha."""
    texto = texto or ""
    if len(texto) <= limite:
        return [texto]

    partes: list[str] = []
    atual = ""
    for linha in texto.split("\n"):
        if len(atual) + len(linha) + 1 > limite:
            if atual:
                partes.append(atual.rstrip())
            # Linha unica maior que o limite: corta na forca.
            while len(linha) > limite:
                partes.append(linha[:limite])
                linha = linha[limite:]
            atual = linha + "\n"
        else:
            atual += linha + "\n"
    if atual.strip():
        partes.append(atual.rstrip())
    return partes


def negrito(texto: str) -> str:
    """Negrito no WhatsApp."""
    return f"*{texto}*"


def italico(texto: str) -> str:
    """Italico no WhatsApp."""
    return f"_{texto}_"
