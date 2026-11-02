"""Memoria del agente (IE3 e IE4).

Tres capas:
  1. Corto plazo  -> historial de mensajes del hilo (checkpointer de LangGraph) + ventana recortada.
  2. Estado de sesión -> EstadoSesion (planificador.py), inyectado en el prompt cada turno.
  3. Largo plazo  -> perfil + pedidos + notas del comensal, persistidos en disco y con
                     recuperación SEMÁNTICA (FAISS) de notas entre sesiones.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.messages import trim_messages
from langgraph.checkpoint.memory import MemorySaver


# ---------------------------------------------------------------- corto plazo
def crear_checkpointer() -> MemorySaver:
    """Memoria de hilo en RAM. Para persistirla basta cambiarla por SqliteSaver/PostgresSaver."""
    return MemorySaver()


def ventana(mensajes: list, max_mensajes: int = 40) -> list:
    """Recorta el historial a los últimos N mensajes, empezando siempre en un mensaje humano
    (para no dejar llamadas a herramientas huérfanas)."""
    return trim_messages(
        mensajes, max_tokens=max_mensajes, token_counter=len, strategy="last",
        start_on="human", include_system=False, allow_partial=False,
    )


# ---------------------------------------------------------------- largo plazo
class MemoriaLargoPlazo:
    def __init__(self, directorio: Path, embeddings: Any):
        self.dir = Path(directorio)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.f_perfiles = self.dir / "perfiles.json"
        self.f_notas = self.dir / "notas.json"
        self.f_pedidos = self.dir / "pedidos.json"
        self.embeddings = embeddings
        self._indice: Optional[FAISS] = None
        self._reconstruir_indice()

    # -- utilidades de persistencia
    @staticmethod
    def _leer(ruta: Path, defecto):
        if not ruta.exists():
            return defecto
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return defecto

    @staticmethod
    def _escribir(ruta: Path, datos) -> None:
        tmp = ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(ruta)

    @staticmethod
    def _ahora() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # -- perfil
    def perfil(self, comensal_id: str) -> dict:
        base = {"alergenos": [], "dietas": [], "preferencia_termica": None, "visitas": 0}
        base.update(self._leer(self.f_perfiles, {}).get(comensal_id, {}))
        return base

    def guardar_perfil(self, comensal_id: str, **campos) -> dict:
        perfiles = self._leer(self.f_perfiles, {})
        actual = self.perfil(comensal_id)
        actual.update(campos)
        perfiles[comensal_id] = actual
        self._escribir(self.f_perfiles, perfiles)
        return actual

    # -- notas (memoria semántica)
    def _reconstruir_indice(self) -> None:
        notas = self._leer(self.f_notas, [])
        if notas:
            self._indice = FAISS.from_texts(
                [n["texto"] for n in notas], self.embeddings,
                metadatas=[{"comensal_id": n["comensal_id"], "tipo": n["tipo"], "fecha": n["fecha"]}
                           for n in notas],
            )

    def agregar_nota(self, comensal_id: str, texto: str, tipo: str = "gusto") -> dict:
        nota = {"comensal_id": comensal_id, "tipo": tipo, "texto": texto.strip(), "fecha": self._ahora()}
        notas = self._leer(self.f_notas, [])
        notas.append(nota)
        self._escribir(self.f_notas, notas)
        meta = [{"comensal_id": comensal_id, "tipo": tipo, "fecha": nota["fecha"]}]
        if self._indice is None:
            self._indice = FAISS.from_texts([nota["texto"]], self.embeddings, metadatas=meta)
        else:
            self._indice.add_texts([nota["texto"]], metadatas=meta)
        return nota

    def recuperar(self, comensal_id: str, consulta: str, k: int = 3) -> list:
        """Recuperación semántica restringida a las notas de ese comensal."""
        if self._indice is None:
            return []
        encontrados = self._indice.similarity_search_with_score(
            consulta, k=k, filter={"comensal_id": comensal_id}, fetch_k=max(20, k * 5))
        return [{"texto": d.page_content, "tipo": d.metadata["tipo"], "fecha": d.metadata["fecha"],
                 "distancia": round(float(s), 3)} for d, s in encontrados]

    # -- pedidos
    def registrar_pedido(self, comensal_id: str, platos: list, total: int, mesa: Optional[str] = None,
                         observaciones: Optional[str] = None) -> dict:
        pedidos = self._leer(self.f_pedidos, [])
        pedido = {"pedido_id": f"P{len(pedidos) + 1:04d}", "comensal_id": comensal_id, "mesa": mesa,
                  "platos": platos, "total": total, "observaciones": observaciones, "fecha": self._ahora()}
        pedidos.append(pedido)
        self._escribir(self.f_pedidos, pedidos)
        return pedido

    def historial_pedidos(self, comensal_id: str) -> list:
        return [p for p in self._leer(self.f_pedidos, []) if p["comensal_id"] == comensal_id]
