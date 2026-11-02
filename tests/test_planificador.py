from planificador import aplicar_cambio, planificar, proponer


def test_plan_sin_restricciones_incluye_tres_etapas(ctx):
    plan = planificar(ctx.estado, ctx.carta)
    assert plan.incluidas() == ["entrada", "fondo", "postre"] and plan.viable


def test_prioridad_fondo_sobre_entrada_y_postre(ctx):
    ctx.estado.presupuesto = 20000   # fondo 12.900 + postre 5.900 = 18.800; entrada ya no cabe
    plan = planificar(ctx.estado, ctx.carta)
    assert plan.incluidas() == ["fondo", "postre"]
    assert "presupuesto insuficiente" in plan.etapas[0].motivo


def test_presupuesto_insuficiente_no_es_viable(ctx):
    ctx.estado.presupuesto = 5000
    plan = planificar(ctx.estado, ctx.carta)
    assert not plan.viable and plan.advertencias


def test_restricciones_combinadas_dejan_una_opcion_por_etapa(ctx):
    ctx.estado.dietas = {"vegetariano", "celiaco"}
    prop = proponer(ctx.estado, ctx.carta, planificar(ctx.estado, ctx.carta))
    assert {e: p.id for e, p in prop["platos"].items()} == {"entrada": "PL003", "fondo": "PL008", "postre": "PL011"}


def test_clima_cambia_la_propuesta(ctx):
    ctx.estado.clima_categoria = "calor"
    calor = proponer(ctx.estado, ctx.carta, planificar(ctx.estado, ctx.carta))
    ctx.estado.clima_categoria = "frio"
    frio = proponer(ctx.estado, ctx.carta, planificar(ctx.estado, ctx.carta))
    assert calor["platos"]["fondo"].id == "PL002"      # neutro > cálido cuando hace calor
    assert frio["platos"]["fondo"].id == "PL008"       # cálido más económico
    assert calor["platos"]["entrada"].perfil_termico == "fresco"


def test_preferencia_expresada_gana_al_clima(ctx):
    ctx.estado.clima_categoria = "calor"
    ctx.estado.preferencia_termica = "calido"
    assert ctx.estado.termica_efectiva() == "calido"


def test_alergia_nueva_descarta_y_reemplaza(ctx):
    ctx.estado.clima_categoria = "calor"
    prop = proponer(ctx.estado, ctx.carta, planificar(ctx.estado, ctx.carta))
    ctx.estado.propuesta = {e: p.id for e, p in prop["platos"].items()}
    assert ctx.estado.propuesta["fondo"] == "PL002"
    ctx.estado.alergenos.add("Pescado")
    rep = aplicar_cambio(ctx.estado, ctx.carta, "alergia nueva")
    assert any("Salmón" in d["plato"] and "Pescado" in d["razon"] for d in rep["descartados"])
    assert ctx.estado.propuesta["fondo"] != "PL002"
    assert rep["nueva_propuesta"] is not None
    assert ctx.estado.eventos[-1].startswith("REPLAN")


def test_presupuesto_menor_descarta_propuesta_que_no_cabe(ctx):
    prop = proponer(ctx.estado, ctx.carta, planificar(ctx.estado, ctx.carta))
    ctx.estado.propuesta = {e: p.id for e, p in prop["platos"].items()}
    ctx.estado.presupuesto = 19000
    rep = aplicar_cambio(ctx.estado, ctx.carta, "presupuesto")
    total = sum(ctx.carta.buscar(i).precio for i in ctx.estado.propuesta.values())
    assert rep["descartados"] and total <= 19000
