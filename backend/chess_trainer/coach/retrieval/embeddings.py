"""Embeddings locais com fastembed (ONNX, CPU): nada de PyTorch no backend (spec §6.2).

O download do modelo (~250 MB) acontece só em `preparar()`, chamado pelo
"Recriar índice"; a criação do objeto é barata e não toca a rede."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

# primeira opção do spec; confirmado em `TextEmbedding.list_supported_models()`
MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DIMENSOES: dict[str, int] = {MODELO_PADRAO: 384}


NAO_BAIXADO = "modelo de embeddings não baixado: use Recriar índice"


class Embeddings(Protocol):
    modelo: str
    dim: int

    def preparar(self, baixar: bool = True) -> None: ...

    def embed(self, textos: list[str]) -> list[list[float]]: ...


class FastembedEmbeddings:
    def __init__(self, modelo: str = MODELO_PADRAO, cache_dir: Path | None = None):
        self.modelo = modelo
        self.dim = DIMENSOES.get(modelo, 384)
        self._cache_dir = cache_dir
        self._model = None

    def preparar(self, baixar: bool = True) -> None:
        """Carrega o modelo. Com `baixar=False` só aceita o que já está em disco
        (`local_files_only` do fastembed): salvar um capítulo nunca pode disparar
        um download de ~250 MB — isso é trabalho do "Recriar índice"."""
        if self._model is not None:
            return
        from fastembed import TextEmbedding  # import tardio: o pacote é pesado

        kwargs = {"model_name": self.modelo}
        if self._cache_dir is not None:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            kwargs["cache_dir"] = str(self._cache_dir)
        if not baixar:
            kwargs["local_files_only"] = True
        try:
            modelo = TextEmbedding(**kwargs)
        except Exception as exc:
            if baixar:
                raise
            raise RuntimeError(NAO_BAIXADO) from exc
        dim = len(next(iter(modelo.embed(["dimensão"]))))
        if dim != self.dim:
            raise RuntimeError(f"modelo {self.modelo}: dimensão {dim}, esperada {self.dim}")
        # só aqui: um modelo que não passou na conferência não fica guardado
        self._model = modelo

    def embed(self, textos: list[str]) -> list[list[float]]:
        if not textos:
            return []
        self.preparar(baixar=False)
        return [list(map(float, v)) for v in self._model.embed(textos)]
