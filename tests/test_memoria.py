from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.messages import AIMessage, HumanMessage

from memoria import MemoriaLargoPlazo, ventana


def test_perfil_persiste_entre_instancias(tmp_path):
    emb = DeterministicFakeEmbedding(size=16)
    m1 = MemoriaLargoPlazo(tmp_path, emb)
    m1.guardar_perfil("ana", alergenos=["Pescado"], dietas=["celiaco"])
    m2 = MemoriaLargoPlazo(tmp_path, emb)   # "nueva sesión"
    assert m2.perfil("ana")["alergenos"] == ["Pescado"]
    assert m2.perfil("otro")["alergenos"] == []


def test_notas_recuperadas_solo_del_comensal_y_persisten(tmp_path):
    emb = DeterministicFakeEmbedding(size=16)
    m1 = MemoriaLargoPlazo(tmp_path, emb)
    m1.agregar_nota("ana", "Le encantó el ceviche vegano", "comentario")
    m1.agregar_nota("beto", "Prefiere carnes rojas", "gusto")
    m2 = MemoriaLargoPlazo(tmp_path, emb)   # el índice FAISS se reconstruye desde disco
    r = m2.recuperar("ana", "ceviche", k=3)
    assert [n["texto"] for n in r] == ["Le encantó el ceviche vegano"]


def test_historial_de_pedidos(tmp_path):
    m = MemoriaLargoPlazo(tmp_path, DeterministicFakeEmbedding(size=16))
    p = m.registrar_pedido("ana", ["A", "B"], 1000, mesa="3")
    assert p["pedido_id"] == "P0001" and len(m.historial_pedidos("ana")) == 1


def test_ventana_recorta_y_empieza_en_mensaje_humano():
    msgs = []
    for i in range(30):
        msgs += [HumanMessage(content=f"h{i}"), AIMessage(content=f"a{i}")]
    r = ventana(msgs, max_mensajes=10)
    assert len(r) <= 10 and isinstance(r[0], HumanMessage) and r[-1].content == "a29"
