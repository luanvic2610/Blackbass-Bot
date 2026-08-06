# chatbot-academia

Chatbot de WhatsApp **multi-cliente**, construído em **FastAPI** e integrado à
**Evolution API**. Cada cliente cadastrado (uma academia, um estúdio etc.) tem seu
próprio número de WhatsApp (sua própria instância na Evolution) e sua própria
configuração (grade de horários, endereço, redes sociais, e-mail da equipe). O bot
recebe mensagens via webhook, descobre de qual cliente é a partir da instância,
interpreta a intenção do aluno e responde com grade de horários, endereço, ou
encaminha para um atendente humano.

---

## Estrutura

```
chatbot-academia/
├── .gitignore
├── README.md
├── requirements.txt
├── .env.example              # template das variáveis de ambiente
├── Dockerfile
├── docker-compose.yml        # para rodar na VPS
├── main.py                   # ponto de entrada (cria o app FastAPI)
├── scripts/
│   ├── bootstrap_db.py        # cria o role bot_app e o schema (roda 1x por Postgres)
│   └── gerenciar_clientes.py  # CLI para cadastrar/editar/(des)ativar clientes
└── src/
    ├── __init__.py           # factory create_app() (abre o pool do banco no startup)
    ├── config.py             # carrega e valida o .env
    ├── db/
    │   ├── pool.py            # pool de conexoes com o Postgres
    │   └── schema.py          # DDL do schema "bot" (idempotente, sem Alembic)
    ├── routes/
    │   └── webhook.py         # POST /webhook + GET /health
    ├── services/
    │   ├── evolution.py       # envio de texto, botões, listas, mídia (por instancia)
    │   ├── clientes.py        # busca a config de cada cliente no banco (com cache)
    │   ├── notificacoes.py    # e-mail para a equipe quando o cliente pede atendente
    │   └── bot_logic.py       # regras de negócio / menu (recebe a config do cliente)
    └── utils/
        └── formatters.py      # telefones, datas, quebra de texto longo
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

1. Suba a Evolution API — veja a seção de deploy abaixo se for usar o
   `docker-compose.yml` deste projeto.
2. Preencha no `.env`:

| Variável | Descrição |
|---|---|
| `EVOLUTION_API_URL` | URL base da Evolution (sem barra no final) |
| `EVOLUTION_API_KEY` | `apikey` global/mestre de autenticação (vale para todas as instâncias) |
| `DATABASE_URL` | conexão com o Postgres onde ficam os clientes cadastrados |
| `WEBHOOK_TOKEN` | token opcional; se preenchido, o webhook exige o header `X-Webhook-Token` |

3. Para cada cliente, crie uma instância na Evolution (ex: `academia-x`) **e**
   cadastre esse mesmo nome via `scripts/gerenciar_clientes.py` (seção
   [Clientes (multi-tenant)](#clientes-multi-tenant) abaixo).
4. Aponte o webhook dessa instância para o seu servidor, habilitando o evento
   **`MESSAGES_UPSERT`** (a mesma URL de webhook serve para todos os clientes —
   a Evolution já manda o nome da instância em cada evento):

```bash
curl -X POST "$EVOLUTION_API_URL/webhook/set/academia-x" \
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

- **Em desenvolvimento**, exponha o localhost com `ngrok http 5000` e use a URL gerada.
- **Em produção com o `docker-compose.yml` deste projeto**, bot e Evolution ficam na
  mesma rede Docker interna, então a URL do webhook é o nome do serviço, sem HTTPS:
  `http://bot:5000/webhook` — não precisa expor o bot publicamente.

---

## Clientes (multi-tenant)

Cada cliente = uma instância da Evolution (um número de WhatsApp) + uma linha na
tabela `bot.clientes` (schema próprio dentro do Postgres que a Evolution já usa,
com um role `bot_app` dedicado — sem acesso às tabelas internas da Evolution).

**Antes do primeiro uso em cada Postgres novo** (local ou VPS) — e antes de subir
o `bot` pela primeira vez, já que ele conecta usando o role `bot_app` — rode:

```bash
docker compose up -d postgres    # so a infra, ainda sem o bot
docker compose run --rm bot python scripts/bootstrap_db.py
```

Isso cria o role `bot_app` (senha vem de `BOT_DB_PASSWORD` no `.env`) e o schema
`bot`, de propriedade dele. Depois disso é so subir o resto normalmente
(`docker compose up -d --build`) e cadastrar os clientes com o script de linha
de comando, rodado dentro do container:

```bash
docker compose exec bot python scripts/gerenciar_clientes.py adicionar \
  --instancia academia-x --nome "Academia X" \
  --telefone "+55 11 90000-0000" --endereco "Rua Exemplo, 123" \
  --email-equipe equipe@academiax.com.br \
  --pix-chave "00.000.000/0001-00" \
  --loja-url "https://loja.academiax.com.br" --loja-cupom "ACADEMIAX10"

docker compose exec bot python scripts/gerenciar_clientes.py definir-grade \
  --instancia academia-x --arquivo grade-academia-x.json

docker compose exec bot python scripts/gerenciar_clientes.py listar
```

Comandos disponíveis: `adicionar`, `listar`, `ver`, `editar`, `definir-grade`,
`exportar-grade`, `ativar`, `desativar`. Rode qualquer um deles com `--help` para
ver todas as opções.

---

## Testando o webhook sem WhatsApp

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event": "messages.upsert",
    "instance": "academia-x",
    "data": {
      "key": {"remoteJid": "5511988887777@s.whatsapp.net", "fromMe": false, "id": "TESTE1"},
      "pushName": "Luan",
      "message": {"conversation": "1"}
    }
  }'
```

---

## Deploy na VPS com Docker

Este projeto sobe **bot + Evolution API + Postgres + Redis + Caddy** juntos. O Caddy
cuida do HTTPS automaticamente (Let's Encrypt) para a Evolution API; o bot fica só na
rede interna, sem exposição pública.

1. Aponte um registro **A** do domínio que você vai usar (ex: `evolution.seudominio.com.br`)
   para o IP público da VPS. O Caddy só emite o certificado se o DNS já estiver resolvendo.
2. Libere as portas 80 e 443 no Security List/NSG da Oracle Cloud (além da regra padrão
   de saída).
3. Preencha o `.env`:

```bash
cp .env.example .env
```

   - `POSTGRES_PASSWORD`: senha forte para o Postgres da Evolution.
   - `BOT_DB_PASSWORD`: outra senha forte, para o role `bot_app` (schema `bot`,
     usado só pelos dados de clientes — isolado das tabelas da Evolution).
   - `EVOLUTION_DOMAIN`: o domínio apontado no passo 1 (ex: `evolution.seudominio.com.br`).
   - `EVOLUTION_API_KEY`: invente uma chave forte — ela vira a `apikey` de autenticação.
   - `EVOLUTION_API_URL=http://evolution:8080` (nome do serviço no compose).
   - `DATABASE_URL` já vem certo no `.env.example` (aponta para o role `bot_app`).

4. Suba a infra e prepare o banco **antes** do bot (ele já conecta como `bot_app`):

```bash
docker compose up -d postgres evolution redis
docker compose run --rm bot python scripts/bootstrap_db.py
docker compose up -d --build
docker compose logs -f evolution   # acompanhe até aparecer "ready"
```

5. Para cada cliente: acesse `https://evolution.seudominio.com.br` (Evolution
   Manager), crie uma instância (ex: `academia-x`) e escaneie o QR code; depois
   cadastre o mesmo nome de instância com
   `docker compose exec bot python scripts/gerenciar_clientes.py adicionar ...`
   (veja a seção [Clientes (multi-tenant)](#clientes-multi-tenant)).
6. Configure o webhook de cada instância apontando para `http://bot:5000/webhook`
   com o evento `MESSAGES_UPSERT` (a mesma URL serve para todas — veja o comando
   `curl` na seção anterior).
7. Teste mandando uma mensagem de WhatsApp para o número conectado.

```bash
docker compose logs -f bot
```

---

## Acessando o banco com pgAdmin (ou outro cliente SQL)

O Postgres da VPS so escuta em `127.0.0.1` do proprio servidor (ver `docker-compose.yml`)
- nunca fica exposto pra internet. Pra usar o pgAdmin da sua maquina, abra um tunel SSH:

```bash
ssh -i <sua-chave> -L 5433:localhost:5432 root@<ip-da-vps> -N
```

Com o tunel aberto, conecte o pgAdmin em `localhost:5433`, banco `evolution`, usando
o usuario `bot_app` e a senha de `BOT_DB_PASSWORD` (so enxerga o schema `bot`, que e
o dos clientes) ou o usuario `evolution` e `POSTGRES_PASSWORD` se precisar ver tambem
as tabelas internas da Evolution.

---

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/webhook` | recebe eventos da Evolution API |
| `POST` | `/webhook/messages-upsert` | mesma rota, caminho alternativo |
| `GET`  | `/health` | healthcheck + variáveis pendentes |

---

## Onde mexer para personalizar

- **Dados de cada cliente (nome, endereço, grade, redes sociais, e-mail da equipe):**
  banco de dados, via `scripts/gerenciar_clientes.py` — não é mais hardcoded no código.
- **Menu e fluxo da conversa:** `src/services/bot_logic.py`.
- **Formato das mensagens enviadas:** `src/services/evolution.py`.
- **Novos endpoints:** crie um `APIRouter` em `src/routes/` e registre em `src/__init__.py`.

> O estado da conversa está em memória (`_ESTADOS` em `bot_logic.py`, chaveado por
> `instancia:numero`). Para múltiplos workers ou reinícios sem perder contexto,
> troque por Redis ou banco.
