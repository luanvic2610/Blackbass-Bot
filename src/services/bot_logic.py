"""Regras de negocio do bot da academia.

Fluxo: recebe o texto do usuario -> decide a resposta -> devolve para a rota,
que usa o servico `evolution` para entregar no WhatsApp.

O estado de conversa fica em memoria (dict). Para producao, troque
`_ESTADOS` por Redis ou banco.
"""

import logging
from datetime import timedelta
from typing import Any

from src.config import settings
from src.utils.formatters import (
    agora_brt,
    dia_da_semana,
    formatar_data,
    negrito,
    normalizar_texto,
    saudacao,
)

logger = logging.getLogger(__name__)

# numero -> {"etapa": str, "dados": dict}
_ESTADOS: dict[str, dict[str, Any]] = {}

# Quanto tempo o bot fica em silencio depois que um humano entra na conversa
# (cliente pediu atendente, ou a equipe mandou mensagem manualmente).
SILENCIO_MINUTOS = 30

# --------------------------------------------------------------------------
# Conteudo (troque por consulta a banco/planilha quando tiver)
# --------------------------------------------------------------------------

GRADE_HORARIOS = {
    "segunda-feira": [
        "09:00 Jiu Jitsu Gi Adulto",
        "18:00 Jiu Jitsu Nogi Adulto",
        "19:00 Jiu Jitsu Kids Gi (6-9 anos)",
        "20:00 Jiu Jitsu Gi Infanto (10-15 anos)",
        "21:00 Jiu Jitsu Gi Adulto",
    ],
    "terca-feira": [
        "08:00 Muay Thai (Misto)",
        "18:15 Jiu Jitsu Baby Gi (3-5 anos)",
        "19:00 Boxe (Misto)",
        "20:00 Muay Thai (Misto)",
    ],
    "quarta-feira": [
        "09:00 Jiu Jitsu Gi Adulto",
        "18:00 Jiu Jitsu Nogi Adulto",
        "19:00 Jiu Jitsu Kids Gi (6-9 anos)",
        "20:00 Jiu Jitsu Gi Infanto (10-15 anos)",
        "21:00 Jiu Jitsu Gi Adulto",
    ],
    "quinta-feira": [
        "08:00 Muay Thai (Misto)",
        "18:00 Jiu Jitsu Nogi Adulto",
        "18:15 Jiu Jitsu Baby Gi (3-5 anos)",
        "19:00 Boxe (Misto)",
        "20:00 Muay Thai (Misto)",
    ],
    "sexta-feira": [
        "09:00 Jiu Jitsu Nogi Adulto",
        "19:00 Jiu Jitsu Gi Feminino",
        "20:00 Jiu Jitsu Gi Infanto (10-15 anos)",
    ],
    "sabado": ["10:00 Capoeira"],
    "domingo": ["Fechado"],
}

HORARIO_FUNCIONAMENTO = (
    "Segunda a sexta: 05h30 as 22h00\n"
    "Sabado: 08h00 as 14h00\n"
    "Domingo e feriados: fechado"
)

GOOGLE_MAPS_URL = "https://maps.app.goo.gl/rv6xNnQ6fLTJF6TC8"
INSTAGRAM_URL = "https://www.instagram.com/teamcruzviana_/"
FORM_AULA_EXPERIMENTAL_URL = "https://forms.gle/g9tQzMD7cuHs7aC29"

OPCOES_MENU = {
    "1": "horarios",
    "2": "aula_experimental",
    "3": "endereco",
    "4": "redes_sociais",
    "5": "atendente",
}

# Palavras que tambem levam a cada opcao.
ATALHOS = {
    "horarios": {"horario", "horarios", "grade", "aula", "aulas", "treino"},
    "endereco": {"endereco", "onde", "local", "localizacao", "mapa", "como chego"},
    "aula_experimental": {"experimental", "aula experimental", "teste", "visita", "agendar"},
    "redes_sociais": {"instagram", "insta", "rede social", "redes sociais", "facebook"},
    "atendente": {"atendente", "humano", "pessoa", "falar com alguem", "suporte"},
}

SAIR = {"menu", "voltar", "sair", "cancelar", "0"}


# --------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------

def obter_estado(numero: str) -> dict[str, Any]:
    return _ESTADOS.setdefault(numero, {"etapa": "inicio", "dados": {}})


def definir_etapa(numero: str, etapa: str) -> None:
    obter_estado(numero)["etapa"] = etapa


def limpar_estado(numero: str) -> None:
    _ESTADOS.pop(numero, None)


def ativar_silencio(numero: str, minutos: int = SILENCIO_MINUTOS) -> None:
    """Faz o bot parar de responder esse numero por `minutos` (renova se ja estava em silencio)."""
    obter_estado(numero)["dados"]["silencio_ate"] = agora_brt() + timedelta(minutes=minutos)


def desativar_silencio(numero: str) -> None:
    obter_estado(numero)["dados"].pop("silencio_ate", None)


def em_silencio(numero: str) -> bool:
    silencio_ate = obter_estado(numero)["dados"].get("silencio_ate")
    return bool(silencio_ate and agora_brt() < silencio_ate)


# --------------------------------------------------------------------------
# Textos
# --------------------------------------------------------------------------

def montar_menu(nome_contato: str = "") -> str:
    ola = f"{saudacao()}{', ' + nome_contato.split()[0] if nome_contato else ''}!"
    return (
        f"{ola} Eu sou o assistente virtual da {negrito(settings.ACADEMIA_NOME)}. "
        "Como posso ajudar?\n\n"
        "1 - Grade de horarios\n"
        "2 - Agendar aula experimental\n"
        "3 - Endereco e funcionamento\n"
        "4 - Redes sociais\n"
        "5 - Falar com um atendente\n\n"
        "_Digite o numero da opcao desejada._"
    )


def montar_horarios(dia: str | None = None) -> str:
    if dia:
        aulas = GRADE_HORARIOS.get(dia, [])
        if not aulas:
            return "Nao encontrei a grade desse dia. Digite *1* para ver a semana inteira."
        corpo = "\n".join(f"- {a}" for a in aulas)
        return f"{negrito('Grade de ' + dia.capitalize())}\n{corpo}"

    blocos = []
    for nome_dia, aulas in GRADE_HORARIOS.items():
        blocos.append(negrito(nome_dia.capitalize()) + "\n" + "\n".join(f"- {a}" for a in aulas))
    rodape = f"\n\nHoje e {dia_da_semana()}, {formatar_data()}.\nDigite *menu* para voltar."
    return f"{negrito('GRADE DE AULAS')}\n\n" + "\n\n".join(blocos) + rodape


def montar_endereco() -> str:
    telefone = f"Telefone: {settings.ACADEMIA_TELEFONE}\n" if settings.ACADEMIA_TELEFONE else ""
    return (
        f"{negrito(settings.ACADEMIA_NOME)}\n"
        f"{settings.ACADEMIA_ENDERECO or 'Endereco nao configurado'}\n"
        f"{telefone}\n"
        f"{negrito('Como chegar')}\n{GOOGLE_MAPS_URL}\n\n"
        f"{negrito('Funcionamento')}\n{HORARIO_FUNCIONAMENTO}\n\n"
        "Digite *menu* para voltar."
    )


def montar_aula_experimental() -> str:
    return (
        f"{negrito('Aula experimental gratuita!')}\n\n"
        "Preencha o formulario abaixo com seus dados e o dia que prefere. "
        "Depois disso sua vaga entra direto na nossa agenda:\n\n"
        f"{FORM_AULA_EXPERIMENTAL_URL}\n\n"
        "Digite *menu* para voltar."
    )


def montar_redes_sociais() -> str:
    return (
        f"{negrito('Redes sociais')}\n\n"
        f"Instagram: {INSTAGRAM_URL}\n\n"
        "Digite *menu* para voltar."
    )


# --------------------------------------------------------------------------
# Nucleo: decide a resposta
# --------------------------------------------------------------------------

def _identificar_intencao(texto: str) -> str | None:
    limpo = normalizar_texto(texto)
    if limpo in OPCOES_MENU:
        return OPCOES_MENU[limpo]
    for intencao, palavras in ATALHOS.items():
        if limpo in palavras or any(p in limpo for p in palavras if len(p) > 4):
            return intencao
    return None


def processar_mensagem(numero: str, texto: str, nome_contato: str = "") -> dict[str, Any]:
    """Recebe a mensagem do usuario e devolve o que o bot deve responder.

    Retorna:
        {"tipo": "texto", "texto": "..."}                      -> enviar_texto
        {"tipo": "encaminhar", "texto": "..."}                 -> notificar atendente
        {"tipo": "ignorar"}                                    -> nao responder
    """
    estado = obter_estado(numero)
    limpo = normalizar_texto(texto)

    if not limpo:
        return {"tipo": "ignorar"}

    # Escape global para o menu: funciona mesmo com o bot em silencio.
    if limpo in SAIR:
        desativar_silencio(numero)
        definir_etapa(numero, "menu")
        return {"tipo": "texto", "texto": montar_menu(nome_contato)}

    # Atendimento humano em andamento (cliente pediu atendente ou a equipe
    # mandou mensagem manualmente): bot fica calado ate o timeout ou ate o
    # cliente digitar "menu" de novo. Cada mensagem nova renova o timeout.
    if em_silencio(numero):
        ativar_silencio(numero)
        return {"tipo": "ignorar"}

    # --- Primeira interacao ---
    if estado["etapa"] == "inicio":
        definir_etapa(numero, "menu")
        intencao = _identificar_intencao(texto)
        if not intencao:
            return {"tipo": "texto", "texto": montar_menu(nome_contato)}
    else:
        intencao = _identificar_intencao(texto)

    # --- Menu ---
    if intencao == "horarios":
        return {"tipo": "texto", "texto": montar_horarios()}

    if intencao == "endereco":
        return {"tipo": "texto", "texto": montar_endereco()}

    if intencao == "redes_sociais":
        return {"tipo": "texto", "texto": montar_redes_sociais()}

    if intencao == "aula_experimental":
        return {"tipo": "texto", "texto": montar_aula_experimental()}

    if intencao == "atendente":
        definir_etapa(numero, "atendimento_humano")
        ativar_silencio(numero)
        return {
            "tipo": "encaminhar",
            "texto": (
                "Certo! Ja avisei nossa equipe. Um atendente responde por aqui "
                "dentro do horario comercial.\n\nDigite *menu* para voltar ao bot."
            ),
        }

    # --- Nao entendeu ---
    return {
        "tipo": "texto",
        "texto": (
            "Nao entendi essa opcao.\n\n" + montar_menu(nome_contato)
        ),
    }
