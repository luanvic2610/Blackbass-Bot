"""Regras de negocio do bot, multi-cliente.

Fluxo: recebe o texto do usuario + a config do cliente (academia) -> decide a
resposta -> devolve para a rota, que usa o servico `evolution` para entregar
no WhatsApp.

O estado de conversa fica em memoria (dict), chaveado por
"{instancia}:{numero}" - assim o mesmo numero de telefone falando com dois
clientes diferentes nao mistura estado/silencio entre eles. Para producao com
mais de 1 worker, troque `_ESTADOS` por Redis ou banco.
"""

import logging
from datetime import timedelta
from typing import Any

from src.services.clientes import ClienteConfig
from src.utils.formatters import (
    agora_brt,
    dia_da_semana,
    formatar_data,
    negrito,
    normalizar_texto,
    saudacao,
)

logger = logging.getLogger(__name__)

# "instancia:numero" -> {"etapa": str, "dados": dict}
_ESTADOS: dict[str, dict[str, Any]] = {}

# Quanto tempo o bot fica em silencio depois que um humano entra na conversa
# (cliente pediu atendente, ou a equipe mandou mensagem manualmente).
SILENCIO_MINUTOS = 30

# --------------------------------------------------------------------------
# Navegacao do bot (nao e dado de negocio por cliente)
# --------------------------------------------------------------------------

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

def _chave(instancia: str, numero: str) -> str:
    return f"{instancia}:{numero}"


def obter_estado(instancia: str, numero: str) -> dict[str, Any]:
    return _ESTADOS.setdefault(_chave(instancia, numero), {"etapa": "inicio", "dados": {}})


def definir_etapa(instancia: str, numero: str, etapa: str) -> None:
    obter_estado(instancia, numero)["etapa"] = etapa


def limpar_estado(instancia: str, numero: str) -> None:
    _ESTADOS.pop(_chave(instancia, numero), None)


def ativar_silencio(instancia: str, numero: str, minutos: int = SILENCIO_MINUTOS) -> None:
    """Faz o bot parar de responder esse numero por `minutos` (renova se ja estava em silencio)."""
    obter_estado(instancia, numero)["dados"]["silencio_ate"] = agora_brt() + timedelta(minutes=minutos)


def desativar_silencio(instancia: str, numero: str) -> None:
    obter_estado(instancia, numero)["dados"].pop("silencio_ate", None)


def em_silencio(instancia: str, numero: str) -> bool:
    silencio_ate = obter_estado(instancia, numero)["dados"].get("silencio_ate")
    return bool(silencio_ate and agora_brt() < silencio_ate)


# --------------------------------------------------------------------------
# Textos
# --------------------------------------------------------------------------

def montar_menu(cliente: ClienteConfig, nome_contato: str = "") -> str:
    ola = f"{saudacao()}{', ' + nome_contato.split()[0] if nome_contato else ''}!"
    return (
        f"{ola} Eu sou o assistente virtual da {negrito(cliente.nome)}. "
        "Como posso ajudar?\n\n"
        "1 - Grade de horarios\n"
        "2 - Agendar aula experimental\n"
        "3 - Endereco e funcionamento\n"
        "4 - Redes sociais\n"
        "5 - Falar com um atendente\n\n"
        "_Digite o numero da opcao desejada._"
    )


def montar_horarios(cliente: ClienteConfig, dia: str | None = None) -> str:
    if dia:
        aulas = cliente.grade_horarios.get(dia, [])
        if not aulas:
            return "Nao encontrei a grade desse dia. Digite *1* para ver a semana inteira."
        corpo = "\n".join(f"- {a}" for a in aulas)
        return f"{negrito('Grade de ' + dia.capitalize())}\n{corpo}"

    blocos = []
    for nome_dia, aulas in cliente.grade_horarios.items():
        blocos.append(negrito(nome_dia.capitalize()) + "\n" + "\n".join(f"- {a}" for a in aulas))
    rodape = f"\n\nHoje e {dia_da_semana()}, {formatar_data()}.\nDigite *menu* para voltar."
    return f"{negrito('GRADE DE AULAS')}\n\n" + "\n\n".join(blocos) + rodape


def montar_endereco(cliente: ClienteConfig) -> str:
    telefone = f"Telefone: {cliente.telefone}\n" if cliente.telefone else ""
    return (
        f"{negrito(cliente.nome)}\n"
        f"{cliente.endereco or 'Endereco nao configurado'}\n"
        f"{telefone}\n"
        f"{negrito('Como chegar')}\n{cliente.google_maps_url}\n\n"
        f"{negrito('Funcionamento')}\n{cliente.horario_funcionamento}\n\n"
        "Digite *menu* para voltar."
    )


def montar_aula_experimental(cliente: ClienteConfig) -> str:
    return (
        f"{negrito('Aula experimental gratuita!')}\n\n"
        "Preencha o formulario abaixo com seus dados e o dia que prefere. "
        "Depois disso sua vaga entra direto na nossa agenda:\n\n"
        f"{cliente.form_aula_experimental_url}\n\n"
        "Digite *menu* para voltar."
    )


def montar_redes_sociais(cliente: ClienteConfig) -> str:
    return (
        f"{negrito('Redes sociais')}\n\n"
        f"Instagram: {cliente.instagram_url}\n\n"
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


def processar_mensagem(
    instancia: str,
    numero: str,
    texto: str,
    cliente: ClienteConfig,
    nome_contato: str = "",
) -> dict[str, Any]:
    """Recebe a mensagem do usuario e devolve o que o bot deve responder.

    Retorna:
        {"tipo": "texto", "texto": "..."}                      -> enviar_texto
        {"tipo": "encaminhar", "texto": "..."}                 -> notificar atendente
        {"tipo": "ignorar"}                                    -> nao responder
    """
    estado = obter_estado(instancia, numero)
    limpo = normalizar_texto(texto)

    if not limpo:
        return {"tipo": "ignorar"}

    # Escape global para o menu: funciona mesmo com o bot em silencio.
    if limpo in SAIR:
        desativar_silencio(instancia, numero)
        definir_etapa(instancia, numero, "menu")
        return {"tipo": "texto", "texto": montar_menu(cliente, nome_contato)}

    # Atendimento humano em andamento (cliente pediu atendente ou a equipe
    # mandou mensagem manualmente): bot fica calado ate o timeout ou ate o
    # cliente digitar "menu" de novo. Cada mensagem nova renova o timeout.
    if em_silencio(instancia, numero):
        ativar_silencio(instancia, numero)
        return {"tipo": "ignorar"}

    # --- Primeira interacao ---
    if estado["etapa"] == "inicio":
        definir_etapa(instancia, numero, "menu")
        intencao = _identificar_intencao(texto)
        if not intencao:
            return {"tipo": "texto", "texto": montar_menu(cliente, nome_contato)}
    else:
        intencao = _identificar_intencao(texto)

    # --- Menu ---
    if intencao == "horarios":
        return {"tipo": "texto", "texto": montar_horarios(cliente)}

    if intencao == "endereco":
        return {"tipo": "texto", "texto": montar_endereco(cliente)}

    if intencao == "redes_sociais":
        return {"tipo": "texto", "texto": montar_redes_sociais(cliente)}

    if intencao == "aula_experimental":
        return {"tipo": "texto", "texto": montar_aula_experimental(cliente)}

    if intencao == "atendente":
        definir_etapa(instancia, numero, "atendimento_humano")
        ativar_silencio(instancia, numero)
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
            "Nao entendi essa opcao.\n\n" + montar_menu(cliente, nome_contato)
        ),
    }
