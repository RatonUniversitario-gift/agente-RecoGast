"""Carga y vectorización de la carta (FAISS). Los embeddings son inyectables para poder testear sin red."""
import json
from pathlib import Path
from typing import Any, List, Optional

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

CAMPOS_REQUERIDOS = {
    "id", "nombre", "categoria", "descripcion", "precio", "alergenos",
    "es_vegetariano", "es_celiaco", "maridaje_sugerido",
}


def crear_embeddings():
    """Modelo local y gratuito (sin API). Import diferido: solo se carga si realmente se usa."""
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def cargar_documentos_desde_json(ruta_json: Path) -> List[Document]:
    if not ruta_json.exists():
        raise FileNotFoundError(f"No se encontró el archivo de datos en: {ruta_json}")
    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            platos: Any = json.load(f)
    except json.JSONDecodeError as error:
        raise ValueError(f"El archivo de menú no contiene JSON válido: {error}") from error
    if not isinstance(platos, list):
        raise ValueError("El archivo de menú debe contener una lista de platos.")

    documentos = []
    for indice, plato in enumerate(platos, start=1):
        if not isinstance(plato, dict) or not CAMPOS_REQUERIDOS.issubset(plato):
            raise ValueError(f"El plato #{indice} no tiene todos los campos requeridos del menú.")
        contenido = (
            f"Plato: {plato['nombre']}\n"
            f"Categoría: {plato['categoria']}\n"
            f"Descripción: {plato['descripcion']}\n"
            f"Precio: ${plato['precio']} CLP\n"
            f"Alérgenos: {', '.join(plato['alergenos']) if plato['alergenos'] else 'Ninguno'}\n"
            f"Apto para Vegetarianos: {'Sí' if plato['es_vegetariano'] else 'No'}\n"
            f"Apto para Celíacos: {'Sí' if plato['es_celiaco'] else 'No'}\n"
            f"Perfil: {plato.get('perfil_termico', 'neutro')}\n"
            f"Maridaje Recomendado: {plato['maridaje_sugerido']}"
        )
        documentos.append(Document(
            page_content=contenido,
            metadata={"id": plato["id"], "nombre": plato["nombre"], "categoria": plato["categoria"]},
        ))
    return documentos


def crear_vector_store(ruta_json: Path, embeddings: Optional[Any] = None) -> FAISS:
    documentos = cargar_documentos_desde_json(ruta_json)
    return FAISS.from_documents(documentos, embeddings or crear_embeddings())


def inicializar_vector_store(ruta_json: Path, embeddings: Optional[Any] = None, k: int = 4):
    """Compatibilidad con la EP1: devuelve un retriever."""
    return crear_vector_store(ruta_json, embeddings).as_retriever(search_kwargs={"k": k})
