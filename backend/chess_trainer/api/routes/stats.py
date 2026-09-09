from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from chess_trainer.api.deps import get_db
from chess_trainer.api.schemas import ProgressOut
from chess_trainer.core.models import utcnow
from chess_trainer.core.stats import progress

router = APIRouter(prefix="/api")


@router.get("/stats/progress", response_model=ProgressOut)
def get_progress(days: int = Query(90, ge=1, le=3650), db: Session = Depends(get_db)):
    """Progresso do período: revisões por dia, rating de táticas, acerto por fonte. Só leitura."""
    now = utcnow()
    return progress(db, since=now - timedelta(days=days), now=now)
