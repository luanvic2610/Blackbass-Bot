"""Regras de negocio do bot da academia.

Fluxo: recebe o texto do usuario -> decide a resposta -> devolve para a rota,
que usa o servico `evolution` para entregar no WhatsApp.

O estado de conversa fica em memoria (dict). Para producao, troque
`_ESTADOS` por Redis ou banco.
"""

import logging
from typing import Any

from src.config import settings
from src.utils.formatters import (
    dia_da_semana,
    formatar_data,
    negrito,
    normalizar_texto,
    saudacao,
)

logger = logging.getLogger(__name__)

# numero -> {"etapa": str, "dados": dict}
_ESTADOS: dict[str, dict[str, Any]] = {}

# --------------------------------------------------------------------------
# Conteudo (troque por consulta a banco/planilha quando tiver)
# --------------------------------------------------------------------------

GRADE_HORARIOS = {
    "segunda-feira": ["06:00 Funcional", "08:00 Pilates", "18:00 Muay Thai", "19:30 Spinning"],
    "terca-feira": ["06:00 Cross", "09:00 Yoga", "18:00 Jiu-Jitsu", "19:30 Zumba"],
    "quarta-feira": ["06:00 Funcional", "08:00 Pilates", "18:00 Muay Thai", "19:30 Spinning"],
    "quinta-feira": ["06:00 Cross", "09:00 Yoga", "18:00 Jiu-Jitsu", "19:30 Zumba"],
    "sexta-feira": ["06:00 Funcional", "08:00 Pilates", "18:00 Muay Thai", "19:00 Alongamento"],
    "sabado": ["08:00 Cross", "10:00 Funcional"],
    "domingo": ["Fechado"],
}

PLANOS = [
    ("Mensal", "R$ 149,90/mes - sem fidelidade"),
    ("Trimestral", "R$ 129,90/mes - fidelidade de 3 meses"),
    ("Anual", "R$ 99,90/mes - fidelidade de 12 meses"),
    ("Diaria", "R$ 25,00 - acesso por 1 dia"),
]

HORARIO_FUNCIONAMENTO = (
    "Segunda a sexta: 05h30 as 22h00\n"
    "Sabado: 08h00 as 14h00\n"
    "Domingo e feriados: fechado"
)

OPCOES_MENU = {
    "1": "horarios",
    "2": "planos",
    "3": "endereco",
    "4": "aula_experimental",
    "5": "atendente",
}

# Palavras que tambem levam a cada opcao.
ATALHOS = {
    "horarios": {"horario", "horarios", "grade", "aula", "aulas", "treino"},
    "planos": {"plano", "planos", "preco", "precos", "valor", "valores", "mensalidade"},
    "endereco": {"endereco", "onde", "local", "localizacao", "mapa", "como chego"},
    "aula_experimental": {"experimental", "aula experimental", "teste", "visita", "agendar"},
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


# --------------------------------------------------------------------------
# Textos
# --------------------------------------------------------------------------

def montar_menu(nome_contato: str = "") -> str:
    ola = f"{saudacao()}{', ' + nome_contato.split()[0] if nome_contato else ''}!"
    return (
        f"{ola} Eu sou o assistente virtual da {negrito(settings.ACADEMIA_NOME)}. "
        "Como posso ajudar?\n\n"
        "1 - Grade de horarios\n"
        "2 - Planos e valores\n"
        "3 - Endereco e funcionamento\n"
        "4 - Agendar aula experimental\n"
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


def montar_planos() -> str:
    linhas = "\n".join(f"- {negrito(nome)}: {desc}" for nome, desc in PLANOS)
    return (
        f"{negrito('PLANOS E VALORES')}\n\n{linhas}\n\n"
        "Matricula gratuita neste mes.\n"
        "Digite *4* para agendar uma aula experimental ou *menu* para voltar."
    )


def montar_endereco() -> str:
    return (
        f"{negrito(settings.ACADEMIA_NOME)}\n"
        f"{settings.ACADEMIA_ENDERECO or 'Endereco nao configurado'}\n"
        f"Telefone: {settings.ACADEMIA_TELEFONE or '-'}\n\n"
        f"{negrito('Funcionamento')}\n{HORARIO_FUNCIONAMENTO}\n\n"
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

    # Escape global para o menu.
    if limpo in SAIR:
        definir_etapa(numero, "menu")
        return {"tipo": "texto", "texto": montar_menu(nome_contato)}

    # --- Fluxo de agendamento de aula experimental ---
    if estado["etapa"] == "aguardando_nome":
        estado["dados"]["nome"] = texto.strip()
        definir_etapa(numero, "aguardando_dia")
        return {
            "tipo": "texto",
            "texto": (
                f"Prazer, {negrito(texto.strip().split()[0])}! "
                "Para qual dia voce quer agendar? (ex: segunda, terca...)"
            ),
        }

    if estado["etapa"] == "aguardando_dia":
        estado["dados"]["dia"] = texto.strip()
        definir_etapa(numero, "menu")
        dados = estado["dados"]
        return {
            "tipo": "encaminhar",
            "texto": (
                f"{negrito('Agendamento registrado!')}\n\n"
                f"Nome: {dados.get('nome')}\n"
                f"Dia: {dados.get('dia')}\n\n"
                "Nossa equipe vai confirmar com voce em instantes.\n"
                "Digite *menu* para voltar ao inicio."
            ),
        }

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

    if intencao == "planos":
        return {"tipo": "texto", "texto": montar_planos()}

    if intencao == "endereco":
        return {"tipo": "texto", "texto": montar_endereco()}

    if intencao == "aula_experimental":
        definir_etapa(numero, "aguardando_nome")
        return {"tipo": "texto", "texto": "Otimo! Qual e o seu nome completo?"}

    if intencao == "atendente":
        definir_etapa(numero, "atendimento_humano")
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
