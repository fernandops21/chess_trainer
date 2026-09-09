from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import ProgressOut
from chess_trainer.core.models import utcnow
from chess_trainer.core.srs.queue import local_day_start
from chess_trainer.core.stats import progress

router = APIRouter(prefix="/api")


@router.get("/stats/progress", response_model=ProgressOut)
def get_progress(days: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db)):
    """Progresso do período: revisões por dia, rating de táticas, acerto por fonte. Só leitura."""
    now = utcnow()
    # o período são `days` dias locais inteiros, contando hoje: `progress()` agrupa
    # por dia local, e cortar no instante deixaria o dia mais antigo pela metade
    since = local_day_start(now) - timedelta(days=days - 1)
    return progress(db, since=since, now=now)
