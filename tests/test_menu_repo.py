from menu_repo import Carta, normalizar_categoria, normalizar_restricciones, normalizar_termica
from conftest import RAIZ

carta = Carta.desde_json(RAIZ / "data" / "menu.json")


def test_normaliza_texto_libre():
    al, di, desc = normalizar_restricciones(["soy celíaco", "alergia a las nueces", "sin lactosa", "polen"])
    assert al == {"Frutos Secos", "Lácteos"}
    assert di == {"celiaco"}
    assert desc == ["polen"]          # lo desconocido no se asume seguro


def test_categoria_y_termica():
    assert normalizar_categoria("algo de entrada") == "Entradas"
    assert normalizar_categoria("plato principal") == "Platos de Fondo"
    assert normalizar_termica("quiero algo reconfortante") is None  # solo acepta términos exactos
    assert normalizar_termica("caliente") == "calido"
    assert normalizar_termica("fresco") == "fresco"


def test_buscar_por_id_y_nombre_parcial():
    assert carta.buscar("PL002").nombre.startswith("Salmón")
    assert carta.buscar("salmon austral").id == "PL002"
    assert carta.buscar("pizza") is None


def test_celiaco_excluye_gluten_y_no_celiacos():
    ids = {p.id for p in carta.aptos(set(), {"celiaco"})}
    assert "PL009" not in ids and "PL010" not in ids and "PL001" not in ids
    assert "PL003" in ids and "PL011" in ids


def test_vegano_excluye_lacteos_y_huevo():
    ids = {p.id for p in carta.aptos(set(), {"vegano"})}
    assert ids == {"PL003", "PL008", "PL011"}


def test_alergeno_explicito_con_motivo():
    ok, motivos = carta.evaluar(carta.buscar("PL002"), {"Pescado"}, set())
    assert not ok and motivos == ["contiene Pescado"]
