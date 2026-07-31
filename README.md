# chatbot-academia

Chatbot de WhatsApp para academia, construído em **Flask** e integrado à **Evolution API**.
Recebe mensagens via webhook, interpreta a intenção do aluno e responde com grade de
horários, planos, endereço ou encaminha para um atendente humano.

---

## Estrutura

```
chatbot-academia/
├── .gitignore
├── README.md
├── requirements.txt
├── .env.example            # template das variáveis de ambiente
├── Dockerfile
├── docker-compose.yml      # para rodar na VPS
├── main.py                 # ponto de entrada (cria o app Flask)
└── src/
    ├── __init__.py         # factory create_app()
    ├── config.py           # carrega e valida o .env
    ├── routes/
    │   └── webhook.py      # POST /webhook + GET /health
    ├── services/
    │   ├── evolution.py    # envio de texto, botões, listas, mídia
    │   └── bot_logic.py    # regras de negócio / menu
    └── utils/
        └── formatters.py   # telefones, datas, quebra de texto longo
```

---

## Rodando localmente

```bash
git clone <url-do-repo>
cd chatbot-academia

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env            # preencha com seus valores
python main.py
```

A API sobe em `http://localhost:5000`. Teste com:

```bash
curl http://localhost:5000/health
```

---

## Configuração da Evolution API

1. Suba a Evolution API e crie uma instância (ex: `blackbass`).
2. Preencha no `.env`:

| Variável | Descrição |
|---|---|
| `EVOLUTION_API_URL` | URL base da Evolution (sem barra no final) |
| `EVOLUTION_API_KEY` | `apikey` de autenticação |
| `EVOLUTION_INSTANCE` | nome da instância |
| `WEBHOOK_TOKEN` | token opcional; se preenchido, o webhook exige o header `X-Webhook-Token` |

3. Aponte o webhook da instância para o seu servidor, habilitando o evento
   **`MESSAGES_UPSERT`**:

```bash
curl -X POST "$EVOLUTION_API_URL/webhook/set/$EVOLUTION_INSTANCE" \
  -H "apikey: $EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://seu-dominio.com/webhook",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

Em desenvolvimento, exponha o localhost com `ngrok http 5000` e use a URL gerada.

---

## Testando o webhook sem WhatsApp

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "data": {
      "key": {"remoteJid": "5511988887777@s.whatsapp.net", "fromMe": false, "id": "TESTE1"},
      "pushName": "Luan",
      "message": {"conversation": "1"}
    }
  }'
```

---

## Deploy na VPS com Docker

```bash
cp .env.example .env    # preencha
docker compose up -d --build
docker compose logs -f bot
```

Coloque um Nginx ou Caddy na frente para servir HTTPS — a Evolution exige URL pública.

---

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/webhook` | recebe eventos da Evolution API |
| `POST` | `/webhook/messages-upsert` | mesma rota, caminho alternativo |
| `GET`  | `/health` | healthcheck + variáveis pendentes |

---

## Onde mexer para personalizar

- **Menu, horários, planos e preços:** `src/services/bot_logic.py` (constantes no topo do arquivo).
- **Formato das mensagens enviadas:** `src/services/evolution.py`.
- **Novos endpoints:** crie um blueprint em `src/routes/` e registre em `src/__init__.py`.

> O estado da conversa está em memória (`_ESTADOS` em `bot_logic.py`). Para múltiplos
> workers ou reinícios sem perder contexto, troque por Redis ou banco.
