"""Testes do nucleo do bot: config por cliente e isolamento de estado entre eles."""

import pytest

from src.services import bot_logic
from src.services.clientes import ClienteConfig


def _cliente(
    instancia: str,
    nome: str,
    endereco: str,
    pix_chave: str = "chave-pix-exemplo",
    loja_url: str = "",
    loja_cupom: str = "",
) -> ClienteConfig:
    return ClienteConfig(
        instancia=instancia,
        nome=nome,
        telefone="",
        endereco=endereco,
        horario_funcionamento="Segunda a sexta: 06h as 22h",
        google_maps_url="https://maps.example.com/" + instancia,
        instagram_url="https://instagram.com/" + instancia,
        form_aula_experimental_url="https://forms.example.com/" + instancia,
        email_equipe=f"equipe@{instancia}.com",
        pix_chave=pix_chave,
        loja_url=loja_url,
        loja_cupom=loja_cupom,
        grade_horarios={"segunda-feira": [f"09:00 Aula da {nome}"]},
        ativo=True,
    )


@pytest.fixture(autouse=True)
def _limpa_estado():
    bot_logic._ESTADOS.clear()
    yield
    bot_logic._ESTADOS.clear()


def test_endereco_reflete_o_cliente_certo():
    cliente_a = _cliente("cliente_a", "Academia A", "Rua A, 1")
    cliente_b = _cliente("cliente_b", "Academia B", "Rua B, 2")
    numero = "5511999990000"

    resposta_a = bot_logic.processar_mensagem("cliente_a", numero, "3", cliente_a)
    resposta_b = bot_logic.processar_mensagem("cliente_b", numero, "3", cliente_b)

    assert "Rua A, 1" in resposta_a["texto"]
    assert "Academia A" in resposta_a["texto"]
    assert "Rua B, 2" in resposta_b["texto"]
    assert "Academia B" in resposta_b["texto"]


def test_grade_reflete_o_cliente_certo():
    cliente_a = _cliente("cliente_a", "Academia A", "Rua A, 1")
    cliente_b = _cliente("cliente_b", "Academia B", "Rua B, 2")
    numero = "5511999990000"

    resposta_a = bot_logic.processar_mensagem("cliente_a", numero, "1", cliente_a)
    resposta_b = bot_logic.processar_mensagem("cliente_b", numero, "1", cliente_b)

    assert "Aula da Academia A" in resposta_a["texto"]
    assert "Aula da Academia B" in resposta_b["texto"]


def test_silencio_nao_vaza_entre_clientes_com_mesmo_numero():
    cliente_a = _cliente("cliente_a", "Academia A", "Rua A, 1")
    cliente_b = _cliente("cliente_b", "Academia B", "Rua B, 2")
    numero = "5511999990000"

    resposta = bot_logic.processar_mensagem("cliente_a", numero, "7", cliente_a)
    assert resposta["tipo"] == "encaminhar"
    assert bot_logic.em_silencio("cliente_a", numero) is True

    # Mesmo numero, cliente diferente: nao deve estar em silencio.
    assert bot_logic.em_silencio("cliente_b", numero) is False
    resposta_b = bot_logic.processar_mensagem("cliente_b", numero, "3", cliente_b)
    assert resposta_b["tipo"] == "texto"
    assert "Rua B, 2" in resposta_b["texto"]


def test_loja_oficial_mostra_link_e_cupom():
    cliente = _cliente(
        "cliente_a", "Academia A", "Rua A, 1",
        loja_url="https://loja.example.com", loja_cupom="DESCONTO10",
    )
    numero = "5511999990000"

    resposta = bot_logic.processar_mensagem("cliente_a", numero, "5", cliente)
    assert resposta["tipo"] == "texto"
    assert "https://loja.example.com" in resposta["texto"]
    assert "DESCONTO10" in resposta["texto"]
    assert "10%" in resposta["texto"]


def test_fluxo_pagamento_pix_ate_aguardar_comprovante():
    cliente = _cliente("cliente_a", "Academia A", "Rua A, 1", pix_chave="12345-chave-pix")
    numero = "5511999990000"

    resposta_menu = bot_logic.processar_mensagem("cliente_a", numero, "6", cliente)
    assert resposta_menu["tipo"] == "texto"
    assert "nome" in resposta_menu["texto"].lower()
    assert bot_logic.aguardando_comprovante_pix("cliente_a", numero) is None

    resposta_pix = bot_logic.processar_mensagem("cliente_a", numero, "Fulano de Tal", cliente)
    assert resposta_pix["tipo"] == "texto"
    assert "12345-chave-pix" in resposta_pix["texto"]
    assert bot_logic.aguardando_comprovante_pix("cliente_a", numero) == "Fulano de Tal"

    # Enquanto so manda texto (nao o comprovante), o bot cobra o arquivo.
    resposta_lembrete = bot_logic.processar_mensagem("cliente_a", numero, "ja paguei", cliente)
    assert resposta_lembrete["tipo"] == "texto"
    assert "Fulano de Tal" in resposta_lembrete["texto"]
    assert bot_logic.aguardando_comprovante_pix("cliente_a", numero) == "Fulano de Tal"

    # "menu" cancela o fluxo em qualquer etapa.
    resposta_cancelar = bot_logic.processar_mensagem("cliente_a", numero, "menu", cliente)
    assert resposta_cancelar["tipo"] == "texto"
    assert bot_logic.aguardando_comprovante_pix("cliente_a", numero) is None
