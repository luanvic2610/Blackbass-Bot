#!/usr/bin/env python3
"""CLI para cadastrar/gerenciar os clientes (academias) do bot.

Cada cliente cadastrado corresponde a uma instancia da Evolution API (um
numero de WhatsApp). Rode de dentro do container:

    docker compose exec bot python scripts/gerenciar_clientes.py <comando> --help
"""

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from psycopg import errors  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from src.config import settings  # noqa: E402
from src.db.schema import ensure_schema  # noqa: E402
from src.utils.formatters import DIAS_SEMANA  # noqa: E402

CAMPOS_TEXTO = (
    "nome", "telefone", "endereco", "horario_funcionamento",
    "google_maps_url", "instagram_url", "form_aula_experimental_url", "email_equipe",
    "pix_chave", "loja_url", "loja_cupom",
)


@contextmanager
def _conectar():
    conn = psycopg.connect(settings.DATABASE_URL)
    try:
        ensure_schema(conn)
        yield conn
    finally:
        conn.close()


def _adicionar_argumentos_campos(parser: argparse.ArgumentParser, obrigatorios: frozenset = frozenset()) -> None:
    parser.add_argument("--nome", required="nome" in obrigatorios)
    parser.add_argument("--telefone", default=None)
    parser.add_argument("--endereco", default=None)
    parser.add_argument("--horario-funcionamento", dest="horario_funcionamento", default=None)
    parser.add_argument("--maps-url", dest="google_maps_url", default=None)
    parser.add_argument("--instagram-url", dest="instagram_url", default=None)
    parser.add_argument("--form-url", dest="form_aula_experimental_url", default=None)
    parser.add_argument("--email-equipe", dest="email_equipe", default=None)
    parser.add_argument("--pix-chave", dest="pix_chave", default=None)
    parser.add_argument("--loja-url", dest="loja_url", default=None)
    parser.add_argument("--loja-cupom", dest="loja_cupom", default=None)


def cmd_adicionar(args: argparse.Namespace) -> None:
    with _conectar() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO bot.clientes (instancia, nome, telefone, endereco,
                        horario_funcionamento, google_maps_url, instagram_url,
                        form_aula_experimental_url, email_equipe, pix_chave,
                        loja_url, loja_cupom)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        args.instancia,
                        args.nome,
                        args.telefone or "",
                        args.endereco or "",
                        args.horario_funcionamento or "",
                        args.google_maps_url or "",
                        args.instagram_url or "",
                        args.form_aula_experimental_url or "",
                        args.email_equipe or "",
                        args.pix_chave or "",
                        args.loja_url or "",
                        args.loja_cupom or "",
                    ),
                )
            except errors.UniqueViolation:
                conn.rollback()
                print(f"Erro: ja existe um cliente com a instancia '{args.instancia}'.", file=sys.stderr)
                sys.exit(1)
        conn.commit()
    print(f"Cliente '{args.instancia}' cadastrado.")


def cmd_listar(args: argparse.Namespace) -> None:
    with _conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if args.todos:
                cur.execute("SELECT instancia, nome, ativo, atualizado_em FROM bot.clientes ORDER BY instancia")
            else:
                cur.execute(
                    "SELECT instancia, nome, ativo, atualizado_em FROM bot.clientes "
                    "WHERE ativo ORDER BY instancia"
                )
            linhas = cur.fetchall()

    if not linhas:
        print("Nenhum cliente cadastrado.")
        return

    print(f"{'instancia':<20} {'nome':<30} {'ativo':<6} atualizado_em")
    for linha in linhas:
        print(f"{linha['instancia']:<20} {linha['nome']:<30} {str(linha['ativo']):<6} {linha['atualizado_em']}")


def cmd_ver(args: argparse.Namespace) -> None:
    with _conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM bot.clientes WHERE instancia = %s", (args.instancia,))
            linha = cur.fetchone()

    if not linha:
        print(f"Cliente '{args.instancia}' nao encontrado.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(linha, indent=2, ensure_ascii=False, default=str))


def cmd_editar(args: argparse.Namespace) -> None:
    atualizacoes = {
        campo: getattr(args, campo)
        for campo in CAMPOS_TEXTO
        if getattr(args, campo) is not None
    }
    if not atualizacoes:
        print("Nenhum campo informado para editar.", file=sys.stderr)
        sys.exit(1)

    colunas = ", ".join(f"{campo} = %s" for campo in atualizacoes)
    valores = list(atualizacoes.values()) + [args.instancia]

    with _conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE bot.clientes SET {colunas}, atualizado_em = now() WHERE instancia = %s",
                valores,
            )
            if cur.rowcount == 0:
                conn.rollback()
                print(f"Cliente '{args.instancia}' nao encontrado.", file=sys.stderr)
                sys.exit(1)
        conn.commit()
    print(f"Cliente '{args.instancia}' atualizado.")


def _definir_ativo(instancia: str, ativo: bool) -> None:
    with _conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bot.clientes SET ativo = %s, atualizado_em = now() WHERE instancia = %s",
                (ativo, instancia),
            )
            if cur.rowcount == 0:
                conn.rollback()
                print(f"Cliente '{instancia}' nao encontrado.", file=sys.stderr)
                sys.exit(1)
        conn.commit()
    print(f"Cliente '{instancia}' {'ativado' if ativo else 'desativado'}.")


def cmd_ativar(args: argparse.Namespace) -> None:
    _definir_ativo(args.instancia, True)


def cmd_desativar(args: argparse.Namespace) -> None:
    _definir_ativo(args.instancia, False)


def _validar_grade(grade: dict) -> None:
    if not isinstance(grade, dict):
        print("Erro: o JSON da grade precisa ser um objeto {dia: [aulas]}.", file=sys.stderr)
        sys.exit(1)
    desconhecidos = set(grade) - set(DIAS_SEMANA)
    if desconhecidos:
        print(f"Erro: dias desconhecidos na grade: {sorted(desconhecidos)}. Use: {DIAS_SEMANA}", file=sys.stderr)
        sys.exit(1)


def cmd_definir_grade(args: argparse.Namespace) -> None:
    caminho = Path(args.arquivo)
    grade = json.loads(caminho.read_text(encoding="utf-8"))
    _validar_grade(grade)

    with _conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bot.clientes SET grade_horarios = %s, atualizado_em = now() WHERE instancia = %s",
                (Jsonb(grade), args.instancia),
            )
            if cur.rowcount == 0:
                conn.rollback()
                print(f"Cliente '{args.instancia}' nao encontrado.", file=sys.stderr)
                sys.exit(1)
        conn.commit()
    print(f"Grade do cliente '{args.instancia}' atualizada ({len(grade)} dia(s)).")


def cmd_exportar_grade(args: argparse.Namespace) -> None:
    with _conectar() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT grade_horarios FROM bot.clientes WHERE instancia = %s", (args.instancia,))
            linha = cur.fetchone()

    if not linha:
        print(f"Cliente '{args.instancia}' nao encontrado.", file=sys.stderr)
        sys.exit(1)

    saida = Path(args.saida) if args.saida else Path(f"grade-{args.instancia}.json")
    saida.write_text(json.dumps(linha["grade_horarios"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Grade exportada para {saida}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gerencia os clientes (academias) cadastrados no bot.")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_adicionar = subparsers.add_parser("adicionar", help="Cadastra um novo cliente.")
    p_adicionar.add_argument("--instancia", required=True, help="Mesmo nome da instancia na Evolution API.")
    _adicionar_argumentos_campos(p_adicionar, obrigatorios=frozenset({"nome"}))
    p_adicionar.set_defaults(func=cmd_adicionar)

    p_listar = subparsers.add_parser("listar", help="Lista os clientes cadastrados.")
    p_listar.add_argument("--todos", action="store_true", help="Inclui clientes desativados.")
    p_listar.set_defaults(func=cmd_listar)

    p_ver = subparsers.add_parser("ver", help="Mostra o registro completo de um cliente.")
    p_ver.add_argument("--instancia", required=True)
    p_ver.set_defaults(func=cmd_ver)

    p_editar = subparsers.add_parser("editar", help="Atualiza campos de um cliente existente.")
    p_editar.add_argument("--instancia", required=True)
    _adicionar_argumentos_campos(p_editar)
    p_editar.set_defaults(func=cmd_editar)

    p_ativar = subparsers.add_parser("ativar", help="Reativa um cliente.")
    p_ativar.add_argument("--instancia", required=True)
    p_ativar.set_defaults(func=cmd_ativar)

    p_desativar = subparsers.add_parser("desativar", help="Desativa um cliente (bot para de responder por ele).")
    p_desativar.add_argument("--instancia", required=True)
    p_desativar.set_defaults(func=cmd_desativar)

    p_definir_grade = subparsers.add_parser("definir-grade", help="Substitui a grade de horarios de um cliente.")
    p_definir_grade.add_argument("--instancia", required=True)
    p_definir_grade.add_argument(
        "--arquivo", required=True, help='JSON no formato {"segunda-feira": ["09:00 ..."], ...}'
    )
    p_definir_grade.set_defaults(func=cmd_definir_grade)

    p_exportar_grade = subparsers.add_parser("exportar-grade", help="Exporta a grade de horarios de um cliente.")
    p_exportar_grade.add_argument("--instancia", required=True)
    p_exportar_grade.add_argument("--saida", default=None, help="Arquivo de saida (padrao: grade-<instancia>.json)")
    p_exportar_grade.set_defaults(func=cmd_exportar_grade)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
