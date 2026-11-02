from typing import Any, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ModeloGuionado(BaseChatModel):
    """LLM de prueba: responde con una secuencia de mensajes predefinida (incluye tool_calls)
    y guarda lo que 'vio' en cada llamada para poder inspeccionar el prompt y la memoria."""
    respuestas: List[Any]
    indice: int = 0
    vistos: List[Any] = []

    @property
    def _llm_type(self) -> str:
        return "guionado"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.vistos.append(list(messages))
        msg = self.respuestas[self.indice]
        self.indice += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def llamada(nombre: str, id_: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": nombre, "args": args, "id": id_}])
