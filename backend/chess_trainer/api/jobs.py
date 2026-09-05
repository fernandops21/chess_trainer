import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Callable

from chess_trainer.core.models import utcnow

ProgressFn = Callable[[str, int, int, str], None]


@dataclass
class JobStatus:
    state: str = "idle"  # idle | running | error
    job: str | None = None
    stage: str = ""
    done: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self.status = JobStatus()

    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, name: str, fn: Callable[[ProgressFn], None]) -> bool:
        with self._lock:
            if self.is_busy:
                return False
            self._cancel.clear()
            self.status = JobStatus(state="running", job=name)
            self._thread = threading.Thread(target=self._run, args=(fn,), daemon=True)
            self._thread.start()
            return True

    def cancel(self) -> bool:
        """Pede parada ao job em andamento; False se não há nada rodando."""
        with self._lock:
            if not self.is_busy:
                return False
            self._cancel.set()
            self.status.cancel_requested = True
            return True

    def should_stop(self) -> bool:
        """Passado aos jobs para que parem entre partidas/meses; o trabalho já commitado fica."""
        return self._cancel.is_set()

    def _run(self, fn: Callable[[ProgressFn], None]) -> None:
        try:
            fn(self.progress)
            self.status.state = "idle"
            if self._cancel.is_set():
                self.status.message = "cancelado"
        except Exception as exc:  # noqa: BLE001 - qualquer falha vira estado de erro visível
            self.status.state = "error"
            self.status.error = str(exc)
        finally:
            self.status.finished_at = utcnow()

    def progress(self, stage: str, done: int, total: int, message: str = "") -> None:
        self.status.stage = stage
        self.status.done = done
        self.status.total = total
        self.status.message = message

    def wait(self, timeout: float = 60.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def snapshot(self) -> dict:
        data = asdict(self.status)
        if data["finished_at"] is not None:
            data["finished_at"] = data["finished_at"].isoformat()
        return data
