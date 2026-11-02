"""Planificación por prioridades y replanificación ante condiciones cambiantes (IE5).

Todo es determinista: el LLM decide CUÁNDO llamar al planificador; las reglas (seguridad,
presupuesto, clima) viven en código, de modo que son verificables y testeables.
"""
from dataclasses import dataclass, field
from itertools import product
from typing import Optional

from menu_repo import Carta, Plato


def clp(n: int) -> str:
    return "$" + f"{n:,}".replace(",", ".")


@dataclass(frozen=True)
class Etapa:
    clave: str
    categoria: str
    prioridad: int  # 1 = más importante


# Orden de servicio (la lista) distinto del orden de prioridad (el número).
ETAPAS_SERVICIO = (
    Etapa("entrada", "Entradas", 2),
    Etapa("fondo", "Platos de Fondo", 1),
    Etapa("postre", "Postres", 3),
)
CLIMA_A_TERMICA = {"calor": "fresco", "frio": "calido", "templado": None}


@dataclass
class EstadoSesion:
    """Estado de trabajo de la sesión. Se inyecta en el prompt en cada turno."""
    comensal_id: str
    alergenos: set = field(default_factory=set)
    dietas: set = field(default_factory=set)
    presupuesto: Optional[int] = None
    preferencia_termica: Optional[str] = None   # expresada por el comensal
    clima_categoria: Optional[str] = None       # 'calor' | 'frio' | 'templado'
    restricciones_confirmadas: bool = False
    propuesta: dict = field(default_factory=dict)  # etapa -> id de plato
    pedido_registrado: bool = False
    eventos: list = field(default_factory=list)

    def termica_efectiva(self) -> Optional[str]:
        return self.preferencia_termica or CLIMA_A_TERMICA.get(self.clima_categoria or "")

    def registrar_evento(self, texto: str) -> None:
        self.eventos.append(texto)


@dataclass
class PlanEtapa:
    etapa: str
    categoria: str
    prioridad: int
    incluida: bool
    motivo: str
    opciones_aptas: int
    costo_minimo: Optional[int]


@dataclass
class Plan:
    etapas: list
    viable: bool
    advertencias: list

    def incluidas(self) -> list:
        return [e.etapa for e in self.etapas if e.incluida]


def planificar(estado: EstadoSesion, carta: Carta) -> Plan:
    """Decide qué etapas del servicio se incluyen.

    Se recorren por PRIORIDAD (fondo > entrada > postre) y se incluye cada una si su opción
    segura más barata cabe en el presupuesto restante. Una etapa sin opciones seguras se omite.
    """
    datos = {}
    for et in ETAPAS_SERVICIO:
        datos[et.clave] = (et, carta.aptos(estado.alergenos, estado.dietas, et.categoria))

    incluidas, motivos, minimos, acumulado = set(), {}, {}, 0
    for et, seguros in sorted(datos.values(), key=lambda x: x[0].prioridad):
        if not seguros:
            motivos[et.clave] = "excluida: sin opciones aptas para las restricciones"
            continue
        minimo = min(p.precio for p in seguros)
        minimos[et.clave] = minimo
        if estado.presupuesto is None or acumulado + minimo <= estado.presupuesto:
            incluidas.add(et.clave)
            acumulado += minimo
            motivos[et.clave] = "incluida"
        else:
            motivos[et.clave] = (
                f"excluida: presupuesto insuficiente (mínimo acumulado {clp(acumulado + minimo)})"
            )

    etapas = [
        PlanEtapa(et.clave, et.categoria, et.prioridad, et.clave in incluidas,
                  motivos[et.clave], len(datos[et.clave][1]), minimos.get(et.clave))
        for et in ETAPAS_SERVICIO
    ]
    viable = "fondo" in incluidas
    advertencias = []
    if not viable:
        advertencias.append(
            "No hay plato de fondo apto dentro de las restricciones y el presupuesto indicados."
        )
    return Plan(etapas, viable, advertencias)


def _afinidad(plato: Plato, termica: Optional[str]) -> int:
    if termica is None or plato.perfil_termico == "neutro":
        return 0
    return 1 if plato.perfil_termico == termica else -1


def proponer(estado: EstadoSesion, carta: Carta, plan: Plan) -> Optional[dict]:
    """Elige la combinación de platos: máxima afinidad térmica; a igualdad, la más económica."""
    etapas = [e for e in plan.etapas if e.incluida]
    if not etapas:
        return None
    opciones = [carta.aptos(estado.alergenos, estado.dietas, e.categoria) for e in etapas]
    termica = estado.termica_efectiva()
    mejor, mejor_clave = None, None
    for combo in product(*opciones):
        total = sum(p.precio for p in combo)
        if estado.presupuesto is not None and total > estado.presupuesto:
            continue
        clave = (sum(_afinidad(p, termica) for p in combo), -total)
        if mejor_clave is None or clave > mejor_clave:
            mejor, mejor_clave = combo, clave
    if mejor is None:
        return None
    return {
        "platos": {e.etapa: p for e, p in zip(etapas, mejor)},
        "total": sum(p.precio for p in mejor),
        "afinidad": mejor_clave[0],
        "termica": termica,
    }


def aplicar_cambio(estado: EstadoSesion, carta: Carta, motivo: str, reproponer: bool = False) -> dict:
    """Replanifica tras un cambio (alergia nueva, presupuesto, clima).

    1) Descarta de la propuesta vigente todo lo que dejó de ser válido.
    2) Si había propuesta y (algo se descartó o se pidió reproponer), calcula una nueva.
    3) Deja registro en estado.eventos (evidencia de comportamiento adaptativo).
    """
    habia_propuesta = bool(estado.propuesta)
    plan = planificar(estado, carta)
    incluidas = set(plan.incluidas())
    descartados = []

    for etapa, pid in list(estado.propuesta.items()):
        plato = carta.buscar(pid)
        razon = None
        if plato is None:
            razon = "ya no existe en la carta"
        else:
            apto, motivos = carta.evaluar(plato, estado.alergenos, estado.dietas)
            if not apto:
                razon = "; ".join(motivos)
            elif etapa not in incluidas:
                razon = "etapa excluida por presupuesto"
        if razon:
            descartados.append({"plato": plato.nombre if plato else pid, "razon": razon})
            del estado.propuesta[etapa]

    if estado.presupuesto is not None and estado.propuesta:
        total = sum(carta.buscar(pid).precio for pid in estado.propuesta.values())
        if total > estado.presupuesto:
            descartados.append({"plato": "propuesta completa",
                                "razon": f"{clp(total)} excede el presupuesto {clp(estado.presupuesto)}"})
            estado.propuesta.clear()

    nueva = None
    if habia_propuesta and (descartados or reproponer):
        anterior = dict(estado.propuesta)
        prop = proponer(estado, carta, plan)
        if prop:
            estado.propuesta = {e: p.id for e, p in prop["platos"].items()}
            nueva = {
                "platos": [{"etapa": e, "id": p.id, "nombre": p.nombre, "precio": p.precio}
                           for e, p in prop["platos"].items()],
                "total": prop["total"], "termica": prop["termica"],
            }
            if anterior != estado.propuesta and not descartados:
                descartados.append({"plato": "propuesta anterior",
                                    "razon": "se ajustó a las nuevas condiciones"})

    resumen = "; ".join(f"{d['plato']} ({d['razon']})" for d in descartados) or "sin cambios en la propuesta"
    estado.registrar_evento(f"REPLAN [{motivo}] -> {resumen}")
    return {"motivo": motivo, "descartados": descartados, "nueva_propuesta": nueva,
            "advertencias": plan.advertencias}


def describir_estado(estado: EstadoSesion, carta: Carta) -> str:
    """Texto compacto que se inyecta en el system prompt en cada turno."""
    plan = planificar(estado, carta)
    lin = [
        f"Comensal: {estado.comensal_id}",
        "Alergias registradas: " + (", ".join(sorted(estado.alergenos)) or "ninguna"),
        "Dietas registradas: " + (", ".join(sorted(estado.dietas)) or "ninguna"),
        "Restricciones confirmadas por el comensal en esta sesión: "
        + ("SÍ" if estado.restricciones_confirmadas else "NO (debes confirmarlas antes de recomendar)"),
        "Presupuesto: " + (clp(estado.presupuesto) if estado.presupuesto else "no indicado"),
        f"Clima: {estado.clima_categoria or 'no consultado'} | preferencia térmica efectiva: "
        f"{estado.termica_efectiva() or 'ninguna'}",
        "Plan (orden de servicio): " + " -> ".join(
            f"{e.etapa}[P{e.prioridad}{'' if e.incluida else ', omitida'}]" for e in plan.etapas),
    ]
    if estado.propuesta:
        nombres = [f"{e}: {carta.buscar(p).nombre}" for e, p in estado.propuesta.items()]
        lin.append("Propuesta vigente: " + "; ".join(nombres))
    else:
        lin.append("Propuesta vigente: ninguna")
    lin.append("Pedido registrado: " + ("sí" if estado.pedido_registrado else "no"))
    return "\n".join(lin)
