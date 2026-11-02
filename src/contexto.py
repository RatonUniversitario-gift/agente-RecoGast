"""Contexto compartido por las herramientas del agente (inyección de dependencias)."""
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from clima_service import obtener_clima_estructurado
from memoria import MemoriaLargoPlazo
from menu_repo import Carta
from planificador import EstadoSesion
from rag_service import crear_embeddings, crear_vector_store


class ClimaCache:
    """Clima con TTL: el agente puede volver a consultarlo durante la sesión sin saturar la API."""

    def __init__(self, fetch: Callable[[], dict] = obtener_clima_estructurado, ttl: int = 600,
                 reloj: Callable[[], float] = time.monotonic):
        self._fetch, self._ttl, self._reloj = fetch, ttl, reloj
        self._dato: Optional[dict] = None
        self._t: float = 0.0

    def obtener(self, forzar: bool = False) -> dict:
        ahora = self._reloj()
        if forzar or self._dato is None or ahora - self._t > self._ttl:
            self._dato, self._t = self._fetch(), ahora
        return self._dato


@dataclass
class Contexto:
    carta: Carta
    vector_store: Any
    memoria: MemoriaLargoPlazo
    clima: ClimaCache
    estado: EstadoSesion
    max_mensajes: int = 40

    @classmethod
    def crear(cls, comensal_id: str, ruta_menu: Path, directorio_memoria: Path,
              embeddings: Optional[Any] = None, clima: Optional[ClimaCache] = None) -> "Contexto":
        embeddings = embeddings or crear_embeddings()
        memoria = MemoriaLargoPlazo(directorio_memoria, embeddings)
        perfil = memoria.perfil(comensal_id)
        memoria.guardar_perfil(comensal_id, visitas=perfil["visitas"] + 1)
        # Lo guardado en el perfil se usa de inmediato (criterio conservador),
        # pero queda "sin confirmar" hasta que el comensal lo ratifique.
        estado = EstadoSesion(
            comensal_id=comensal_id, alergenos=set(perfil["alergenos"]), dietas=set(perfil["dietas"]),
            preferencia_termica=perfil.get("preferencia_termica"),
        )
        return cls(carta=Carta.desde_json(ruta_menu), vector_store=crear_vector_store(ruta_menu, embeddings),
                   memoria=memoria, clima=clima or ClimaCache(), estado=estado)
