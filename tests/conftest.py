import sys
from pathlib import Path

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from contexto import ClimaCache, Contexto  # noqa: E402


class ClimaFalso:
    """Clima controlable desde el test (simula condiciones cambiantes)."""
    def __init__(self, categoria="templado", temp=18.0):
        self.categoria, self.temp = categoria, temp

    def __call__(self):
        return {"disponible": True, "temperatura": self.temp, "codigo": 0,
                "descripcion": "despejado", "categoria": self.categoria}


@pytest.fixture
def clima():
    return ClimaFalso()


@pytest.fixture
def ctx(tmp_path, clima):
    return Contexto.crear("ana", RAIZ / "data" / "menu.json", tmp_path / "mem",
                          embeddings=DeterministicFakeEmbedding(size=32),
                          clima=ClimaCache(fetch=clima, ttl=0))


@pytest.fixture
def herramientas(ctx):
    from herramientas import crear_herramientas
    return {t.name: t for t in crear_herramientas(ctx)}
