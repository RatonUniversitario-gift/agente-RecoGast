"""Prueba de integración del grafo del agente con un LLM guionado (sin red ni API key)."""
import json

from langchain_core.messages import AIMessage, ToolMessage

from agent import construir_agente
from fakes import ModeloGuionado, llamada


def test_flujo_multi_turno_memoria_y_replanificacion(ctx, clima):
    clima.categoria = "calor"
    llm = ModeloGuionado(respuestas=[
        # turno 1: el agente confirma restricciones, consulta clima y planifica
        llamada("registrar_restricciones", "c1", alergias=["gluten"], presupuesto=40000),
        llamada("consultar_clima", "c2"),
        llamada("planificar_comida", "c3"),
        AIMessage(content="Te propongo un menú sin gluten."),
        # turno 2: el comensal declara una alergia nueva -> debe re-registrar
        llamada("registrar_restricciones", "c4", alergias=["pescado"]),
        AIMessage(content="Ajusté la propuesta: descarté el pescado."),
        # turno 3: pregunta por algo dicho al inicio (memoria de corto plazo)
        AIMessage(content="Dijiste que tu presupuesto era de $40.000."),
    ], vistos=[])
    agente = construir_agente(ctx, llm=llm)
    cfg = {"configurable": {"thread_id": "t1"}, "recursion_limit": 25}

    agente.invoke({"messages": [("user", "Soy celíaco, tengo 40 mil")]}, cfg)
    assert ctx.estado.restricciones_confirmadas and ctx.estado.propuesta
    assert ctx.estado.propuesta["fondo"] == "PL002"          # calor -> neutro
    # el system prompt de la 2.ª llamada ya incluye el estado actualizado
    assert "Gluten" in llm.vistos[1][0].content and "calor" not in llm.vistos[0][0].content

    agente.invoke({"messages": [("user", "Ah, y soy alérgico al pescado")]}, cfg)
    assert "Pescado" in ctx.estado.alergenos
    assert ctx.estado.propuesta["fondo"] != "PL002"
    assert any(ev.startswith("REPLAN") for ev in ctx.estado.eventos)

    agente.invoke({"messages": [("user", "¿cuál era mi presupuesto?")]}, cfg)
    ultima_llamada = llm.vistos[-1]
    textos = [m.content for m in ultima_llamada if getattr(m, "type", "") == "human"]
    assert "Soy celíaco, tengo 40 mil" in textos             # el historial del hilo sigue disponible
    assert "Pescado" in ultima_llamada[0].content            # y el estado vigente va en el system prompt


def test_memoria_de_largo_plazo_entre_sesiones(ctx, tmp_path, clima):
    from contexto import ClimaCache, Contexto
    from langchain_core.embeddings import DeterministicFakeEmbedding
    from conftest import RAIZ

    llm = ModeloGuionado(respuestas=[
        llamada("registrar_restricciones", "a", alergias=["nueces"], preferencia_termica="fresco"),
        llamada("guardar_nota", "b", texto="Celebra su cumpleaños", tipo="ocasion"),
        AIMessage(content="Listo."),
    ], vistos=[])
    construir_agente(ctx, llm=llm).invoke({"messages": [("user", "hola")]},
                                         {"configurable": {"thread_id": "s1"}, "recursion_limit": 25})

    # Nueva sesión (nuevo Contexto, nuevo hilo) sobre el mismo directorio de memoria
    ctx2 = Contexto.crear("ana", RAIZ / "data" / "menu.json", ctx.memoria.dir,
                          embeddings=DeterministicFakeEmbedding(size=32), clima=ClimaCache(fetch=clima))
    assert ctx2.estado.alergenos == {"Frutos Secos"}
    assert ctx2.estado.preferencia_termica == "fresco"
    assert ctx2.estado.restricciones_confirmadas is False     # hay que ratificarlas con el comensal
    assert ctx2.memoria.perfil("ana")["visitas"] == 2
    assert ctx2.memoria.recuperar("ana", "cumpleaños")[0]["texto"] == "Celebra su cumpleaños"




def test_herramientas_se_ejecutan_en_orden_con_max_concurrency(ctx):
    """Gemini suele emitir varias llamadas en un solo mensaje; planificar_comida depende de
    registrar_restricciones, así que deben ejecutarse en orden (config max_concurrency=1)."""
    llm = ModeloGuionado(respuestas=[
        AIMessage(content="", tool_calls=[
            {"name": "registrar_restricciones", "args": {"alergias": ["pescado"]}, "id": "a"},
            {"name": "planificar_comida", "args": {}, "id": "b"}]),
        AIMessage(content="ok"),
    ], vistos=[])
    agente = construir_agente(ctx, llm=llm)
    agente.invoke({"messages": [("user", "hola")]},
                  {"configurable": {"thread_id": "p"}, "recursion_limit": 25, "max_concurrency": 1})
    tipos = [ev.split(" ")[0] for ev in ctx.estado.eventos]
    assert tipos.index("REPLAN") < tipos.index("PLAN")