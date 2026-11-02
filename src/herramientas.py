"""Herramientas del agente, agrupadas por tipo (IE1).

  CONSULTA     buscar_menu, consultar_clima, recuperar_memoria
  RAZONAMIENTO verificar_alergenos, planificar_comida, calcular_cuenta
  ESCRITURA    registrar_restricciones, guardar_nota, registrar_pedido

Las que protegen al comensal (alérgenos) son deterministas: el LLM las invoca, pero la decisión
de seguridad se toma en código (menu_repo.Carta.evaluar).
"""
import json
from typing import Optional

from langchain_core.tools import BaseTool, tool

from contexto import Contexto
from menu_repo import normalizar_categoria, normalizar_restricciones, normalizar_termica
from planificador import aplicar_cambio, clp, planificar, proponer


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def crear_herramientas(ctx: Contexto) -> list:
    e, carta = ctx.estado, ctx.carta

    # ------------------------------------------------------------------ CONSULTA
    @tool
    def buscar_menu(consulta: str, categoria: Optional[str] = None) -> str:
        """Búsqueda semántica (RAG) en la carta del restaurante.
        Devuelve SOLO platos aptos para las restricciones registradas y lista aparte los que
        descartó por seguridad. 'categoria' es opcional: Entradas, Platos de Fondo o Postres."""
        cat = normalizar_categoria(categoria)
        docs = ctx.vector_store.similarity_search(consulta, k=len(carta.platos))
        aptos, descartados = [], []
        for d in docs:
            p = carta.buscar(d.metadata["id"])
            if cat and p.categoria != cat:
                continue
            ok, motivos = carta.evaluar(p, e.alergenos, e.dietas)
            if ok:
                aptos.append(p.ficha())
            else:
                descartados.append({"plato": p.nombre, "motivos": motivos})
        salida = {"resultados": aptos[:4], "descartados_por_seguridad": descartados}
        if not e.restricciones_confirmadas:
            salida["advertencia"] = ("Las restricciones del comensal NO están confirmadas. "
                                     "Pregúntalas y usa registrar_restricciones antes de recomendar.")
        return _json(salida)

    @tool
    def consultar_clima(forzar: bool = False) -> str:
        """Consulta el clima actual (Open-Meteo, con caché de 10 min). Úsala antes de recomendar y de
        nuevo si la conversación es larga o el comensal menciona un cambio de clima (forzar=true).
        Si el clima cambia de categoría, replanifica automáticamente la propuesta vigente."""
        datos = ctx.clima.obtener(forzar)
        if not datos["disponible"]:
            return _json({"disponible": False,
                          "mensaje": "Clima no disponible: no lo consideres en la recomendación."})
        previo = e.clima_categoria
        e.clima_categoria = datos["categoria"]
        salida = {"disponible": True, "temperatura": datos["temperatura"],
                  "descripcion": datos["descripcion"], "categoria": datos["categoria"],
                  "preferencia_termica_efectiva": e.termica_efectiva()}
        if previo is None:
            e.registrar_evento(f"CLIMA [{datos['categoria']}, {datos['temperatura']}°C]")
        elif previo != datos["categoria"]:
            salida["replanificacion"] = aplicar_cambio(
                e, carta, f"cambio de clima {previo} -> {datos['categoria']}", reproponer=True)
        return _json(salida)

    @tool
    def recuperar_memoria(consulta: str) -> str:
        """Recupera de la memoria de largo plazo el perfil del comensal y las notas de visitas
        anteriores más relevantes para la consulta (recuperación semántica)."""
        perfil = ctx.memoria.perfil(e.comensal_id)
        return _json({
            "perfil": {k: perfil[k] for k in ("alergenos", "dietas", "preferencia_termica", "visitas")},
            "notas_relevantes": ctx.memoria.recuperar(e.comensal_id, consulta),
            "pedidos_anteriores": [
                {"fecha": p["fecha"], "platos": p["platos"], "total": p["total"]}
                for p in ctx.memoria.historial_pedidos(e.comensal_id)[-3:]],
        })

    # --------------------------------------------------------------- RAZONAMIENTO
    @tool
    def verificar_alergenos(platos: list[str]) -> str:
        """Verifica de forma determinista si cada plato (id o nombre) es apto para las restricciones
        registradas. Es la única fuente válida para afirmar que un plato es seguro."""
        res = []
        for ref in platos:
            p = carta.buscar(ref)
            if p is None:
                res.append({"consulta": ref, "error": "plato no encontrado en la carta"})
                continue
            ok, motivos = carta.evaluar(p, e.alergenos, e.dietas)
            res.append({"id": p.id, "plato": p.nombre, "apto": ok, "motivos": motivos,
                        "alergenos_del_plato": list(p.alergenos)})
        salida = {"resultados": res}
        if not e.restricciones_confirmadas:
            salida["advertencia"] = "Restricciones no confirmadas con el comensal."
        return _json(salida)

    @tool
    def planificar_comida(presupuesto: Optional[int] = None) -> str:
        """Planifica el servicio (entrada, fondo, postre) por prioridades y propone una combinación
        segura, dentro del presupuesto y acorde al clima. Si se entrega 'presupuesto' (CLP) se
        actualiza y se replanifica. Requiere restricciones confirmadas."""
        if not e.restricciones_confirmadas:
            return _json({"error": "Primero confirma alergias y dietas con el comensal y regístralas "
                                   "con registrar_restricciones (si no tiene, envía listas vacías)."})
        cambio = None
        if presupuesto is not None and presupuesto != e.presupuesto:
            e.presupuesto = int(presupuesto)
            cambio = aplicar_cambio(e, carta, f"presupuesto {clp(e.presupuesto)}")
        plan = planificar(e, carta)
        prop = proponer(e, carta, plan)
        if prop:
            e.propuesta = {et: p.id for et, p in prop["platos"].items()}
        else:
            e.propuesta = {}
        e.registrar_evento("PLAN [" + ", ".join(plan.incluidas()) + "]" +
                           (f" total {clp(prop['total'])}" if prop else " sin propuesta viable"))
        return _json({
            "plan": [{"etapa": p.etapa, "prioridad": p.prioridad, "incluida": p.incluida,
                      "motivo": p.motivo, "opciones_aptas": p.opciones_aptas,
                      "costo_minimo": p.costo_minimo} for p in plan.etapas],
            "propuesta": None if not prop else {
                "platos": [dict(p.ficha(), etapa=et) for et, p in prop["platos"].items()],
                "total": prop["total"], "criterio_termico": prop["termica"]},
            "advertencias": plan.advertencias,
            "replanificacion_por_presupuesto": cambio,
        })

    @tool
    def calcular_cuenta(platos: list[str], propina_pct: int = 10) -> str:
        """Calcula subtotal, propina sugerida (por defecto 10%) y total de una lista de platos (id o
        nombre), y lo compara con el presupuesto si existe."""
        ps, faltan = [], []
        for ref in platos:
            p = carta.buscar(ref)
            (ps if p else faltan).append(p or ref)
        sub = sum(p.precio for p in ps)
        propina = round(sub * propina_pct / 100)
        salida = {"platos": [p.nombre for p in ps], "subtotal": sub, "propina": propina,
                  "total": sub + propina, "no_encontrados": faltan}
        if e.presupuesto is not None:
            salida["presupuesto"] = e.presupuesto
            salida["subtotal_dentro_de_presupuesto"] = sub <= e.presupuesto
            salida["diferencia"] = e.presupuesto - sub
        return _json(salida)

    # ------------------------------------------------------------------- ESCRITURA
    @tool
    def registrar_restricciones(alergias: list[str] = [], dietas: list[str] = [],
                                presupuesto: Optional[int] = None,
                                preferencia_termica: Optional[str] = None,
                                reemplazar: bool = False) -> str:
        """Registra (y guarda en el perfil de largo plazo) alergias, dietas (celíaco, vegetariano,
        vegano), presupuesto en CLP y preferencia térmica (fresco/caliente). Por defecto AGREGA a lo
        existente; reemplazar=true sobrescribe. Llamarla con listas vacías confirma que el comensal NO
        tiene restricciones. Replanifica si cambia algo."""
        antes = (set(e.alergenos), set(e.dietas), e.presupuesto, e.termica_efectiva())
        alerg, diet, desconocidas = normalizar_restricciones((alergias or []) + (dietas or []))
        if reemplazar:
            e.alergenos, e.dietas = alerg, diet
        else:
            e.alergenos |= alerg
            e.dietas |= diet
        if presupuesto is not None:
            e.presupuesto = int(presupuesto)
        termica = normalizar_termica(preferencia_termica)
        if termica:
            e.preferencia_termica = termica
        e.restricciones_confirmadas = True
        ctx.memoria.guardar_perfil(e.comensal_id, alergenos=sorted(e.alergenos), dietas=sorted(e.dietas),
                                   preferencia_termica=e.preferencia_termica)
        salida = {"alergenos": sorted(e.alergenos), "dietas": sorted(e.dietas),
                  "presupuesto": e.presupuesto, "preferencia_termica": e.preferencia_termica,
                  "no_reconocidas": desconocidas}
        if desconocidas:
            salida["accion"] = ("Hay restricciones que no pude mapear a la carta: pregunta al comensal "
                                "y avísale que no puedo garantizar esos ingredientes.")
        despues = (set(e.alergenos), set(e.dietas), e.presupuesto, e.termica_efectiva())
        if antes != despues:
            salida["replanificacion"] = aplicar_cambio(e, carta, "restricciones/presupuesto actualizados")
        return _json(salida)

    @tool
    def guardar_nota(texto: str, tipo: str = "gusto") -> str:
        """Guarda en la memoria de largo plazo una nota útil para futuras visitas (gustos, ocasión,
        comentarios sobre un plato). 'tipo': gusto, ocasion o comentario."""
        nota = ctx.memoria.agregar_nota(e.comensal_id, texto, tipo)
        e.registrar_evento(f"NOTA [{tipo}] {nota['texto']}")
        return _json({"guardada": True, "nota": nota["texto"]})

    @tool
    def registrar_pedido(platos: list[str], mesa: Optional[str] = None,
                         observaciones: Optional[str] = None) -> str:
        """Registra el pedido definitivo. Antes de escribir, RE-VERIFICA cada plato contra las
        restricciones: si alguno no es apto, rechaza todo el pedido. Requiere restricciones
        confirmadas y la aprobación explícita del comensal."""
        if not e.restricciones_confirmadas:
            return _json({"error": "No se puede registrar: las restricciones no están confirmadas."})
        ps, rechazos = [], []
        for ref in platos:
            p = carta.buscar(ref)
            if p is None:
                rechazos.append({"plato": ref, "motivos": ["no existe en la carta"]})
                continue
            ok, motivos = carta.evaluar(p, e.alergenos, e.dietas)
            if not ok:
                rechazos.append({"plato": p.nombre, "motivos": motivos})
            else:
                ps.append(p)
        if rechazos or not ps:
            e.registrar_evento("PEDIDO RECHAZADO: " + "; ".join(
                f"{r['plato']} ({', '.join(r['motivos'])})" for r in rechazos))
            return _json({"registrado": False, "rechazos": rechazos})
        total = sum(p.precio for p in ps)
        pedido = ctx.memoria.registrar_pedido(e.comensal_id, [p.nombre for p in ps], total, mesa, observaciones)
        ctx.memoria.agregar_nota(e.comensal_id, "Pidió: " + ", ".join(p.nombre for p in ps), "pedido")
        e.pedido_registrado = True
        e.registrar_evento(f"PEDIDO {pedido['pedido_id']} {clp(total)}")
        return _json({"registrado": True, "pedido_id": pedido["pedido_id"], "total": total})

    return [buscar_menu, consultar_clima, recuperar_memoria,
            verificar_alergenos, planificar_comida, calcular_cuenta,
            registrar_restricciones, guardar_nota, registrar_pedido]
