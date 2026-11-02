"""Acceso determinista a la carta: búsqueda por id/nombre y evaluación de seguridad alimentaria.

Esta capa NO usa LLM: la regla de alérgenos se valida aquí, en código, y no solo en el prompt.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


def norm(texto: str) -> str:
    """Minúsculas, sin tildes y sin espacios sobrantes."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t.lower()).strip()


ALIAS_ALERGENOS = {
    "gluten": "Gluten", "trigo": "Gluten", "harina": "Gluten",
    "lacteos": "Lácteos", "lactosa": "Lácteos", "leche": "Lácteos", "queso": "Lácteos",
    "huevo": "Huevo", "huevos": "Huevo",
    "frutos secos": "Frutos Secos", "nuez": "Frutos Secos", "nueces": "Frutos Secos",
    "mani": "Frutos Secos", "almendra": "Frutos Secos", "almendras": "Frutos Secos",
    "pescado": "Pescado", "pescados": "Pescado",
    "moluscos": "Moluscos", "molusco": "Moluscos", "mariscos": "Moluscos", "marisco": "Moluscos",
    "soya": "Soya", "soja": "Soya",
    "sesamo": "Sésamo",
}
ALIAS_DIETAS = {
    "celiaco": "celiaco", "celiaca": "celiaco", "celiaquia": "celiaco",
    "vegetariano": "vegetariano", "vegetariana": "vegetariano",
    "vegano": "vegano", "vegana": "vegano",
}
_ALIAS_TERMICOS = {
    "fresco": "fresco", "frio": "fresco", "ligero": "fresco", "liviano": "fresco", "refrescante": "fresco",
    "calido": "calido", "caliente": "calido", "reconfortante": "calido", "abrigador": "calido",
}
CATEGORIAS = ("Entradas", "Platos de Fondo", "Postres")


def normalizar_restricciones(textos: Iterable[str]):
    """Traduce texto libre ('soy celíaco', 'alergia a las nueces') a alérgenos y dietas canónicos.

    Devuelve (alergenos, dietas, no_reconocidas). Lo no reconocido NO se asume seguro.
    """
    alergenos, dietas, desconocidas = set(), set(), []
    claves = sorted({**ALIAS_ALERGENOS, **ALIAS_DIETAS}, key=len, reverse=True)
    for bruto in textos or []:
        t = norm(bruto)
        if not t:
            continue
        hallado = False
        for clave in claves:
            if re.search(rf"\b{re.escape(clave)}\b", t):
                hallado = True
                if clave in ALIAS_ALERGENOS:
                    alergenos.add(ALIAS_ALERGENOS[clave])
                else:
                    dietas.add(ALIAS_DIETAS[clave])
                t = re.sub(rf"\b{re.escape(clave)}\b", " ", t)
        if not hallado:
            desconocidas.append(bruto)
    return alergenos, dietas, desconocidas


def normalizar_termica(texto: Optional[str]) -> Optional[str]:
    return _ALIAS_TERMICOS.get(norm(texto)) if texto else None


def normalizar_categoria(texto: Optional[str]) -> Optional[str]:
    t = norm(texto or "")
    if "entrad" in t:
        return "Entradas"
    if "fondo" in t or "principal" in t:
        return "Platos de Fondo"
    if "postre" in t:
        return "Postres"
    return None


@dataclass(frozen=True)
class Plato:
    id: str
    nombre: str
    categoria: str
    descripcion: str
    precio: int
    alergenos: tuple
    es_vegetariano: bool
    es_celiaco: bool
    maridaje: str
    perfil_termico: str = "neutro"

    def ficha(self) -> dict:
        return {
            "id": self.id, "nombre": self.nombre, "categoria": self.categoria,
            "precio": self.precio, "alergenos": list(self.alergenos),
            "perfil_termico": self.perfil_termico, "maridaje": self.maridaje,
            "descripcion": self.descripcion,
        }


class Carta:
    def __init__(self, platos: list):
        self.platos = list(platos)

    @classmethod
    def desde_json(cls, ruta: Path) -> "Carta":
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return cls([
            Plato(
                id=d["id"], nombre=d["nombre"], categoria=d["categoria"],
                descripcion=d["descripcion"], precio=int(d["precio"]),
                alergenos=tuple(d["alergenos"]), es_vegetariano=bool(d["es_vegetariano"]),
                es_celiaco=bool(d["es_celiaco"]), maridaje=d["maridaje_sugerido"],
                perfil_termico=d.get("perfil_termico", "neutro"),
            ) for d in datos
        ])

    def buscar(self, ref: str) -> Optional[Plato]:
        """Busca por id exacto, nombre exacto o coincidencia parcial de nombre."""
        if not ref:
            return None
        r = norm(ref)
        for p in self.platos:
            if norm(p.id) == r:
                return p
        for p in self.platos:
            if norm(p.nombre) == r:
                return p
        for p in self.platos:
            if r in norm(p.nombre) or norm(p.nombre) in r:
                return p
        return None

    def evaluar(self, plato: Plato, alergenos: set, dietas: set):
        """Regla de seguridad: devuelve (apto, motivos). Es conservadora: ante duda, no apto."""
        motivos = []
        for a in sorted(alergenos):
            if a in plato.alergenos:
                motivos.append(f"contiene {a}")
        if "celiaco" in dietas and (not plato.es_celiaco or "Gluten" in plato.alergenos):
            motivos.append("no es apto para celíacos")
        if "vegetariano" in dietas and not plato.es_vegetariano:
            motivos.append("no es vegetariano")
        if "vegano" in dietas:
            if not plato.es_vegetariano:
                motivos.append("no es vegano")
            elif "Lácteos" in plato.alergenos or "Huevo" in plato.alergenos:
                motivos.append("contiene derivados animales (lácteos/huevo)")
        return (not motivos), motivos

    def aptos(self, alergenos: set, dietas: set, categoria: Optional[str] = None) -> list:
        return [
            p for p in self.platos
            if (categoria is None or p.categoria == categoria)
            and self.evaluar(p, alergenos, dietas)[0]
        ]
