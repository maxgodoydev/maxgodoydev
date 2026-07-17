#!/usr/bin/env python3
"""Gera um card com as linguagens dos repositórios públicos do usuário.

A automação consulta a API de linguagens do GitHub, soma os bytes detectados
em cada repositório público e produz percentuais no estilo "Most Used
Languages". A métrica representa composição dos projetos, não proficiência.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"

COLORS = [
    "#18B8B2",
    "#FF5A4F",
    "#C25491",
    "#6C3FA0",
    "#5367A5",
    "#F05A2A",
    "#7D8B72",
    "#C7A24A",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default=os.getenv("GITHUB_USER", "maxgodoydev"))
    parser.add_argument("--token", default=os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN"))
    parser.add_argument("--top", type=int, default=int(os.getenv("TOP_LANGUAGES", "6")))
    parser.add_argument("--output-dir", default="assets/generated")
    parser.add_argument(
        "--exclude-repo",
        action="append",
        default=[],
        help="Repositório completo no formato owner/name. Pode ser repetido.",
    )
    return parser.parse_args()


def github_request(url: str, token: str | None, attempts: int = 3) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "maxgodoydev-profile-language-stats",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {403, 429, 500, 502, 503, 504} and attempt < attempts:
                time.sleep(attempt * 2)
                continue
            raise RuntimeError(f"GitHub API respondeu {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt < attempts:
                time.sleep(attempt * 2)
                continue
            raise RuntimeError(f"Falha de rede ao consultar GitHub: {exc}") from exc

    raise RuntimeError("Falha inesperada ao consultar a API do GitHub.")


def list_public_repositories(user: str, token: str | None) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1

    while page <= 10:
        params = urllib.parse.urlencode(
            {
                "type": "owner",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        payload = github_request(f"{API_ROOT}/users/{user}/repos?{params}", token)
        if not payload:
            break
        repositories.extend(payload)
        if len(payload) < 100:
            break
        page += 1

    return repositories


def select_repositories(
    repositories: list[dict[str, Any]],
    excluded_repositories: set[str],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for repository in repositories:
        full_name = str(repository.get("full_name", ""))
        if not full_name or full_name.lower() in excluded_repositories:
            continue
        if repository.get("fork") or repository.get("archived"):
            continue
        if repository.get("private"):
            continue
        selected.append(repository)
    return selected


def collect_language_bytes(
    repositories: list[dict[str, Any]],
    token: str | None,
) -> tuple[dict[str, int], dict[str, set[str]]]:
    totals: dict[str, int] = defaultdict(int)
    language_repositories: dict[str, set[str]] = defaultdict(set)

    for index, repository in enumerate(repositories, start=1):
        full_name = repository["full_name"]
        print(f"[{index}/{len(repositories)}] analisando {full_name}")
        payload = github_request(f"{API_ROOT}/repos/{full_name}/languages", token)
        for language, size in payload.items():
            amount = int(size or 0)
            if amount <= 0:
                continue
            totals[language] += amount
            language_repositories[language].add(full_name)

    return dict(totals), dict(language_repositories)


def summarize(
    totals: dict[str, int],
    language_repositories: dict[str, set[str]],
    top: int,
) -> list[dict[str, Any]]:
    total_bytes = sum(totals.values())
    if total_bytes <= 0:
        return []

    ordered = sorted(totals.items(), key=lambda pair: pair[1], reverse=True)
    rows: list[dict[str, Any]] = []

    for language, size in ordered[:top]:
        rows.append(
            {
                "language": language,
                "bytes": size,
                "percentage": round(size / total_bytes * 100, 2),
                "repositories": len(language_repositories.get(language, set())),
            }
        )

    remaining = ordered[top:]
    if remaining:
        remaining_bytes = sum(size for _, size in remaining)
        remaining_repositories: set[str] = set()
        for language, _ in remaining:
            remaining_repositories.update(language_repositories.get(language, set()))
        rows.append(
            {
                "language": "Outros",
                "bytes": remaining_bytes,
                "percentage": round(remaining_bytes / total_bytes * 100, 2),
                "repositories": len(remaining_repositories),
            }
        )

    return rows


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_svg(
    rows: list[dict[str, Any]],
    *,
    theme: str,
    repository_count: int,
    generated_at: str,
) -> str:
    dark = theme == "dark"
    background = "#12111D" if dark else "#FFFFFF"
    border = "#D7D3E0" if dark else "#D0CBD8"
    title = "#FF3F98" if dark else "#B51F68"
    text = "#C8F4F1" if dark else "#263238"
    muted = "#AAA7B5" if dark else "#6D6877"
    track = "#252331" if dark else "#ECE8F0"

    width = 1000
    height = 330 if not rows else 345
    bar_x = 80
    bar_y = 112
    bar_width = 840
    bar_height = 22

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">Linguagens dos meus projetos</title>',
        '<desc id="desc">Percentuais das linguagens detectadas nos repositórios públicos.</desc>',
        '<style>',
        "  text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
        '</style>',
        f'<rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="18" fill="{background}" stroke="{border}" stroke-width="3"/>',
        f'<text x="80" y="67" fill="{title}" font-size="34" font-weight="750">Linguagens dos meus projetos</text>',
    ]

    if not rows:
        parts.extend(
            [
                f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="11" fill="{track}"/>',
                f'<text x="500" y="205" text-anchor="middle" fill="{text}" font-size="22" font-weight="700">Aguardando a primeira sincronização</text>',
                f'<text x="500" y="240" text-anchor="middle" fill="{muted}" font-size="16">Actions → Atualizar linguagens dos projetos → Run workflow</text>',
            ]
        )
    else:
        total_percentage = sum(float(row["percentage"]) for row in rows) or 100.0
        x = bar_x
        for index, row in enumerate(rows):
            color = COLORS[index % len(COLORS)]
            if index == len(rows) - 1:
                segment_width = bar_x + bar_width - x
            else:
                segment_width = round(bar_width * float(row["percentage"]) / total_percentage)
            if segment_width <= 0:
                continue
            parts.append(
                f'<rect x="{x}" y="{bar_y}" width="{segment_width}" height="{bar_height}" fill="{color}"/>'
            )
            x += segment_width
        parts.append(
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" rx="11" fill="none" stroke="{background}" stroke-width="2"/>'
        )

        for index, row in enumerate(rows[:8]):
            column = index % 2
            line = index // 2
            base_x = 80 if column == 0 else 560
            y = 182 + line * 42
            color = COLORS[index % len(COLORS)]
            parts.extend(
                [
                    f'<circle cx="{base_x}" cy="{y - 6}" r="9" fill="{color}"/>',
                    f'<text x="{base_x + 22}" y="{y}" fill="{text}" font-size="18">{escape(row["language"])} {float(row["percentage"]):.2f}%</text>',
                ]
            )

    footer_y = height - 25
    parts.append(
        f'<text x="920" y="{footer_y}" text-anchor="end" fill="{muted}" font-size="13">{repository_count} repositórios · atualizado em {escape(generated_at)}</text>'
    )
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def write_outputs(
    output_dir: Path,
    rows: list[dict[str, Any]],
    *,
    user: str,
    repository_count: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    generated_at = now.strftime("%d/%m/%Y")

    payload = {
        "user": user,
        "generated_at": now.isoformat(),
        "metric": "github_linguist_bytes",
        "repositories_analyzed": repository_count,
        "languages": rows,
        "notes": [
            "O repositório do perfil, forks e repositórios arquivados são desconsiderados.",
            "Os percentuais usam os bytes retornados pela API de linguagens do GitHub.",
            "A métrica representa composição dos projetos, não proficiência.",
        ],
    }

    (output_dir / "language-activity.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for theme in ("dark", "light"):
        (output_dir / f"language-activity-{theme}.svg").write_text(
            render_svg(
                rows,
                theme=theme,
                repository_count=repository_count,
                generated_at=generated_at,
            ),
            encoding="utf-8",
        )


def main() -> int:
    args = parse_args()
    if args.top <= 0:
        print("top deve ser maior que zero.", file=sys.stderr)
        return 2

    excluded = {repo.lower() for repo in args.exclude_repo}
    excluded.add(f"{args.user}/{args.user}".lower())

    repositories = list_public_repositories(args.user, args.token)
    selected = select_repositories(repositories, excluded)
    totals, language_repositories = collect_language_bytes(selected, args.token)
    rows = summarize(totals, language_repositories, args.top)

    write_outputs(
        Path(args.output_dir),
        rows,
        user=args.user,
        repository_count=len(selected),
    )

    print(f"{len(selected)} repositórios analisados.")
    print(f"Arquivos atualizados em {args.output_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
