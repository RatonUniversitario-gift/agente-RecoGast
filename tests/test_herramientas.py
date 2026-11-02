import json


def run(h, nombre, **args):
    return json.loads(h[nombre].invoke(args))


def test_planificar_exige_confirmar_restricciones(herramientas):
    assert "error" in run(herramientas, "planificar_comida")


def test_registrar_pedido_exige_confirmar_restricciones(herramientas):
    assert "error" in run(herramientas, "registrar_pedido", platos=["PL003"])


def test_registrar_restricciones_y_no_reconocidas(herramientas, ctx):
    r = run(herramientas, "registrar_restricciones", alergias=["pescado", "polen"], dietas=["celíaco"])
    assert r["alergenos"] == ["Pescado"] and r["dietas"] == ["celiaco"] and r["no_reconocidas"] == ["polen"]
    assert "accion" in r and ctx.estado.restricciones_confirmadas
    assert ctx.memoria.perfil("ana")["alergenos"] == ["Pescado"]      # persistió en largo plazo


def test_buscar_menu_filtra_por_seguridad(herramientas):
    run(herramientas, "registrar_restricciones", alergias=["pescado"])
    r = run(herramientas, "buscar_menu", consulta="algo del mar", categoria="entradas")
    nombres = [x["nombre"] for x in r["resultados"]]
    assert all("Atún" not in n for n in nombres)
    assert any("Atún" in d["plato"] for d in r["descartados_por_seguridad"])


def test_registrar_pedido_rechaza_plato_no_apto(herramientas, ctx):
    run(herramientas, "registrar_restricciones", dietas=["celiaco"])
    r = run(herramientas, "registrar_pedido", platos=["PL003", "PL009"])
    assert r["registrado"] is False and r["rechazos"][0]["plato"].startswith("Sorrentinos")
    assert ctx.memoria.historial_pedidos("ana") == []                  # nada se escribió


def test_pedido_valido_escribe_pedido_y_nota(herramientas, ctx):
    run(herramientas, "registrar_restricciones", alergias=[], dietas=[])
    r = run(herramientas, "registrar_pedido", platos=["PL003", "PL008"], mesa="4")
    assert r["registrado"] and r["total"] == 22700
    assert ctx.memoria.historial_pedidos("ana")[0]["mesa"] == "4"
    assert ctx.memoria.recuperar("ana", "pedido")[0]["tipo"] == "pedido"


def test_presupuesto_replanifica(herramientas, ctx):
    run(herramientas, "registrar_restricciones", alergias=[])
    p1 = run(herramientas, "planificar_comida")
    assert [e["etapa"] for e in p1["plan"] if e["incluida"]] == ["entrada", "fondo", "postre"]
    p2 = run(herramientas, "planificar_comida", presupuesto=20000)
    assert [e["etapa"] for e in p2["plan"] if e["incluida"]] == ["fondo", "postre"]
    assert p2["propuesta"]["total"] <= 20000


def test_cambio_de_clima_replanifica_propuesta_vigente(herramientas, ctx, clima):
    run(herramientas, "registrar_restricciones", alergias=[])
    clima.categoria = "calor"
    run(herramientas, "consultar_clima")
    run(herramientas, "planificar_comida")
    assert ctx.estado.propuesta["fondo"] == "PL002"
    clima.categoria = "frio"
    r = run(herramientas, "consultar_clima", forzar=True)
    assert r["replanificacion"]["nueva_propuesta"] is not None
    assert ctx.estado.propuesta["fondo"] == "PL008"


def test_clima_no_disponible_degrada_sin_romper(herramientas, ctx):
    ctx.clima._fetch = lambda: {"disponible": False}
    r = run(herramientas, "consultar_clima", forzar=True)
    assert r["disponible"] is False and ctx.estado.clima_categoria is None


def test_calcular_cuenta_con_presupuesto(herramientas, ctx):
    ctx.estado.presupuesto = 20000
    r = run(herramientas, "calcular_cuenta", platos=["PL003", "PL008"])
    assert r["subtotal"] == 22700 and r["propina"] == 2270 and r["subtotal_dentro_de_presupuesto"] is False


def test_verificar_alergenos(herramientas):
    run(herramientas, "registrar_restricciones", alergias=["gluten"])
    r = run(herramientas, "verificar_alergenos", platos=["Sorrentinos", "PL003", "pizza"])["resultados"]
    assert r[0]["apto"] is False and r[1]["apto"] is True and "error" in r[2]
