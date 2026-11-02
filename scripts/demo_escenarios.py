"""Demostración reproducible SIN LLM ni API key: ejecuta las herramientas y el planificador sobre
escenarios de condiciones cambiantes. Sirve como evidencia para IE5/IE7 (ver docs/pruebas.md).

    python scripts/demo_escenarios.py
"""
import json
import sys
import tempfile
from pathlib import Path

from langchain_core.embeddings import DeterministicFakeEmbedding

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

from contexto import ClimaCache, Contexto  # noqa: E402
from herramientas import crear_herramientas  # noqa: E402
from planificador import describir_estado  # noqa: E402

CLIMA = {"categoria": "templado", "temp": 18.0}


def clima_falso():
    return {"disponible": True, "temperatura": CLIMA["temp"], "codigo": 0,
            "descripcion": "despejado", "categoria": CLIMA["categoria"]}


def nuevo(directorio, comensal="demo"):
    ctx = Contexto.crear(comensal, RAIZ / "data" / "menu.json", directorio,
                         embeddings=DeterministicFakeEmbedding(size=32), clima=ClimaCache(fetch=clima_falso, ttl=0))
    return ctx, {t.name: t for t in crear_herramientas(ctx)}


def llamar(h, nombre, **args):
    print(f"  > {nombre}({json.dumps(args, ensure_ascii=False)})")
    return json.loads(h[nombre].invoke(args))


def propuesta(r):
    p = r.get("propuesta") or r.get("nueva_propuesta")
    if not p:
        return "(sin propuesta)"
    return " | ".join(f"{x.get('etapa')}: {x['nombre']}" for x in p["platos"]) + f"  -> total ${p['total']:,}"


def titulo(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def main():
    tmp = Path(tempfile.mkdtemp())

    titulo("Escenario 1 - Seguridad: el sistema bloquea un pedido no apto (celíaco)")
    ctx, h = nuevo(tmp / "s1")
    print(" ", llamar(h, "planificar_comida"))
    llamar(h, "registrar_restricciones", dietas=["celíaco"])
    r = llamar(h, "registrar_pedido", platos=["Sorrentinos de Calabaza", "Ceviche Vegano"])
    print("  ->", r)

    titulo("Escenario 2 - Presupuesto cambiante: replanificación por prioridades")
    ctx, h = nuevo(tmp / "s2")
    llamar(h, "registrar_restricciones", alergias=[])
    for pres in (None, 20000, 5000):
        r = llamar(h, "planificar_comida", **({"presupuesto": pres} if pres else {}))
        incl = [e["etapa"] for e in r["plan"] if e["incluida"]]
        print(f"  -> etapas incluidas: {incl} | {propuesta(r)}")
        for adv in r["advertencias"]:
            print("  !!", adv)

    titulo("Escenario 3 - Clima cambiante: la propuesta se ajusta a mitad de conversación")
    ctx, h = nuevo(tmp / "s3")
    llamar(h, "registrar_restricciones", alergias=[])
    CLIMA.update(categoria="calor", temp=31.0)
    llamar(h, "consultar_clima")
    print("  ->", propuesta(llamar(h, "planificar_comida")))
    CLIMA.update(categoria="frio", temp=8.0)
    r = llamar(h, "consultar_clima", forzar=True)
    print("  ->", r["replanificacion"]["descartados"], "\n  ->", propuesta(r["replanificacion"]))

    titulo("Escenario 4 - Alergia declarada a mitad de conversación")
    CLIMA.update(categoria="calor", temp=30.0)
    ctx, h = nuevo(tmp / "s4")
    llamar(h, "registrar_restricciones", alergias=[])
    llamar(h, "consultar_clima")
    print("  ->", propuesta(llamar(h, "planificar_comida")))
    r = llamar(h, "registrar_restricciones", alergias=["pescado"])
    print("  ->", r["replanificacion"]["descartados"], "\n  ->", propuesta(r["replanificacion"]))
    print("\n" + describir_estado(ctx.estado, ctx.carta))
    print("\nBitácora de eventos:"); print("\n".join("  - " + e for e in ctx.estado.eventos))

    titulo("Escenario 5 - Memoria de largo plazo: segunda visita")
    ctx, h = nuevo(tmp / "s5", "lucia")
    llamar(h, "registrar_restricciones", alergias=["nueces"], dietas=["vegetariano"], preferencia_termica="fresco")
    llamar(h, "guardar_nota", texto="Celebra su cumpleaños y le encantó el ceviche vegano", tipo="ocasion")
    llamar(h, "registrar_pedido", platos=["PL003", "PL008", "PL011"], mesa="2")
    ctx2, h2 = nuevo(tmp / "s5", "lucia")   # nueva sesión: nuevo Contexto, mismo disco
    print("  Estado inicial 2.ª visita:", sorted(ctx2.estado.alergenos), sorted(ctx2.estado.dietas),
          "| confirmadas:", ctx2.estado.restricciones_confirmadas)
    print("  ->", llamar(h2, "recuperar_memoria", consulta="cumpleaños"))


if __name__ == "__main__":
    main()
