import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from sqlalchemy.orm import Session

from chess_trainer.core.analysis.mistakes import Thresholds
from chess_trainer.core.models import Setting
from chess_trainer.core.puzzles.generator import PuzzleConfig


@dataclass
class AppSettings:
    chesscom_username: str = ""
    categories: list[str] = field(default_factory=lambda: ["rapid", "daily", "classical"])
    stockfish_path: str = ""
    analysis_depth: int = 18
    puzzle_depth: int = 20
    mistake_threshold_cp: int = 100
    blunder_threshold_cp: int = 200
    avoid_gap_cp: int = 150
    new_per_day: int = 10
    # ordem dos exercícios novos: "random" (sorteada) ou "recent" (partida mais recente primeiro)
    new_order: str = "random"
    leech_lapses: int = 5
    analysis_seconds: int = 15
    puzzle_search_seconds: int = 20
    tactics_rating: int = 1200
    tactics_window: int = 150
    lichess_min_plays: int = 2000
    lichess_min_popularity: int = 90
    # token pessoal do explorador de aberturas; fica só neste banco e nunca sai pela API
    lichess_token: str = ""
    # classifica os lances (brilhante, erro, imprecisão etc.) durante a análise
    classify_moves: bool = True
    # ao errar, mostra a réplica da engine e a queda de avaliação
    refute_wrong_moves: bool = True
    # --- treinador com IA (spec 2026-09-11) ---
    # chave da API da Anthropic: só neste banco, nunca sai pela API
    anthropic_api_key: str = ""
    coach_model: str = "claude-opus-5"
    coach_effort: str = "high"
    # LangFuse (observabilidade): host vazio = desligado; a chave secreta nunca sai pela API
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    row = db.get(Setting, key)
    return json.loads(row.value) if row else default


def set_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)
    db.commit()


def load_settings(db: Session) -> AppSettings:
    values: dict[str, Any] = {}
    for f in fields(AppSettings):
        stored = get_setting(db, f.name, None)
        if stored is not None:
            values[f.name] = stored
    return AppSettings(**values)


def save_settings(db: Session, settings: AppSettings) -> AppSettings:
    settings.chesscom_username = settings.chesscom_username.strip().lower()
    # token colado costuma vir com espaços em volta; só espaços equivale a apagar
    settings.lichess_token = settings.lichess_token.strip()
    settings.anthropic_api_key = settings.anthropic_api_key.strip()
    settings.langfuse_public_key = settings.langfuse_public_key.strip()
    settings.langfuse_secret_key = settings.langfuse_secret_key.strip()
    settings.langfuse_host = settings.langfuse_host.strip().rstrip("/")
    for key, value in asdict(settings).items():
        set_setting(db, key, value)
    return settings


def thresholds_from(settings: AppSettings) -> Thresholds:
    return Thresholds(
        mistake_cp=settings.mistake_threshold_cp,
        blunder_cp=settings.blunder_threshold_cp,
    )


def puzzle_config_from(settings: AppSettings) -> PuzzleConfig:
    return PuzzleConfig(
        depth=settings.puzzle_depth,
        avoid_gap_cp=settings.avoid_gap_cp,
        # a resposta do adversário usa a mesma profundidade e o mesmo tempo do lance do solver
        search_seconds=settings.puzzle_search_seconds,
    )
