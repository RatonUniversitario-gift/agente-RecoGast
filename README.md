# RecoGast — Agente gastronómico (EP2 · ISY0101)

Evolución del asistente RAG de la EP1 a un **agente autónomo** que atiende a un comensal por turnos:
confirma sus restricciones, consulta el clima, planifica un servicio (entrada · fondo · postre) dentro
del presupuesto, **replanifica** cuando cambian las condiciones y registra el pedido, recordando al
comensal entre visitas.

> Regla de seguridad no negociable: las alergias y dietas se validan **en código** (`src/menu_repo.py`),
> no solo en el prompt. Ningún plato no apto puede ser recomendado por las herramientas ni registrado
> como pedido, aunque el LLM se equivoque.

## Arquitectura (resumen)

```
Comensal (CLI) ─► Agente ReAct (LangGraph + Gemini)
                    │  prompt dinámico = instrucciones + ESTADO de sesión + ventana de mensajes
                    ▼
        ┌───────────────────── 9 herramientas ─────────────────────┐
        │ Consulta:     buscar_menu · consultar_clima · recuperar_memoria
        │ Razonamiento: verificar_alergenos · planificar_comida · calcular_cuenta
        │ Escritura:    registrar_restricciones · guardar_nota · registrar_pedido
        └───────────────────────────────────────────────────────────┘
              │                    │                       │
   menu.json + FAISS         Open-Meteo (TTL)      data/memoria (perfil, pedidos, notas + FAISS)
```

Diagramas completos (arquitectura, secuencia, estados, memoria): **[`docs/orquestacion.md`](docs/orquestacion.md)**.

## Requisitos

- Python 3.11+
- API key de Google AI Studio (https://aistudio.google.com/apikey)
- (opcional) API key de HF con permisos de solo lectura (https://huggingface.co/settings/tokens)
- Internet (Gemini, Open-Meteo y la primera descarga del modelo de embeddings)

## Instalación

```bash
git clone (https://github.com/RatonUniversitario-gift/agente-RecoGast)
cd agente-RecoGast

python -m venv venv
# Windows: venv\Scripts\activate      Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz:

```
GOOGLE_API_KEY=tu_clave
GOOGLE_MODEL=gemini-3.5-flash-lite 
(opcional) HF_TOKEN=tu_clave
```

## Ejecución

```bash
python src/main.py --comensal ana --mesa 5
```

| Comando | Acción |
|---|---|
| `/plan` | Muestra el estado de la sesión (restricciones, presupuesto, clima, plan, propuesta) |
| `/perfil` | Muestra el perfil guardado en la memoria de largo plazo |
| `/eventos` | Bitácora de decisiones (`PLAN`, `REPLAN`, `CLIMA`, `PEDIDO`…) |
| `/salir` | Termina |

Mientras el agente trabaja, la consola imprime cada `[herramienta]` que invoca (trazabilidad).
Usa el mismo `--comensal` en otra ejecución para ver la memoria de largo plazo en acción.

Ejemplo de conversación:

```
Comensal > soy celíaco y tengo 40 mil
  [herramienta] registrar_restricciones({"dietas": ["celíaco"], "presupuesto": 40000})
  [herramienta] consultar_clima({})
  [herramienta] planificar_comida({})
RecoGast > Te propongo: Ceviche vegano… + Salmón Austral… (sin gluten, fresco por el calor)…
Comensal > ah, y soy alérgico al pescado
  [herramienta] registrar_restricciones({"alergias": ["pescado"]})
RecoGast > Ajusté el plan: descarté el salmón y propongo…
```

## Pruebas

```bash
pip install -r requirements-dev.txt
python -m pytest -q                      # 32 pruebas, sin red ni API key
python scripts/demo_escenarios.py        # escenarios de replanificación, sin LLM
```

Evidencia: [`docs/pruebas.md`](docs/pruebas.md), `docs/evidencia_pytest.txt`, `docs/evidencia_demo.txt`.

## Estructura

```
├── data/menu.json            # Carta (ahora con perfil_termico por plato)
├── data/memoria/             # Memoria de largo plazo (se genera; fuera de git)
├── src/
│   ├── main.py               # CLI y bucle de conversación
│   ├── agent.py              # Agente ReAct (LangGraph) + prompt dinámico
│   ├── herramientas.py       # Las 9 herramientas
│   ├── planificador.py       # Prioridades, propuesta, replanificación, EstadoSesion
│   ├── menu_repo.py          # Carta y regla de seguridad (determinista)
│   ├── memoria.py            # Checkpointer, ventana de mensajes, memoria de largo plazo
│   ├── contexto.py           # Dependencias compartidas + caché de clima
│   ├── rag_service.py        # Vectorización de la carta (FAISS, MiniLM local)
│   └── clima_service.py      # Open-Meteo (con categorización calor/frío/templado)
├── tests/                    # pytest (LLM guionado + embeddings falsos)
├── scripts/demo_escenarios.py
└── docs/                     # orquestación, pruebas, evidencias, diagrama EP1
```

## Cómo se cubre la pauta

| Indicador | Dónde |
|---|---|
| IE1 Herramientas autónomas | `herramientas.py`: 9 herramientas (consulta, razonamiento, escritura) elegidas por el LLM |
| IE2 Framework | LangGraph `create_react_agent` + LangChain (herramientas, FAISS, embeddings); ver decisiones |
| IE3 Memoria de contenido | Checkpointer por hilo, `EstadoSesion` en el prompt, perfil y pedidos persistentes (`memoria.py`) |
| IE4 Recuperación semántica | `buscar_menu` (carta) y `recuperar_memoria` (notas de visitas previas), ambas con FAISS |
| IE5 Planificación | `planificador.py`: prioridades fondo > entrada > postre, presupuesto, clima, `REPLAN` |
| IE6 / IE8 Documentación | Este README + `docs/orquestacion.md` |
| IE7 Decisiones adaptativas | Escenarios 2–4 de `docs/pruebas.md` y `scripts/demo_escenarios.py` |

## Decisiones de diseño

| Decisión | Justificación |
|---|---|
| **LangGraph ReAct** en lugar de `AgentExecutor` | Es el camino recomendado en LangChain 0.3 para agentes con estado; trae checkpointer de hilo y permite un prompt dinámico por turno. |
| **Seguridad en código, no en el prompt** | Un LLM puede fallar; las alergias son un riesgo real. `Carta.evaluar` filtra `buscar_menu`, valida `verificar_alergenos` y re-verifica en `registrar_pedido`. |
| **Gates deterministas** | `planificar_comida` y `registrar_pedido` se niegan a operar sin restricciones confirmadas. |
| **Planificador determinista** | Reglas de prioridad/presupuesto verificables y testeables; el LLM decide *cuándo* planificar, no *cómo*. |
| **Estado de sesión inyectado en el prompt** | Mantiene la coherencia aunque `trim_messages` descarte turnos antiguos. |
| **Clima como herramienta con caché TTL** | Resuelve la limitación de la EP1 (clima una sola vez por sesión): el agente decide cuándo refrescarlo. |
| **Perfil guardado pero “sin confirmar”** | En una nueva visita se usa de inmediato (criterio conservador) pero se pide ratificarlo. |
| **Embeddings locales y FAISS en memoria** | Sin costo ni infraestructura; los embeddings son inyectables para testear sin red. |

## Limitaciones y trabajo futuro

- `MemorySaver` vive en RAM: el historial de mensajes se pierde al cerrar; el estado relevante sí persiste
  vía perfil/notas. Para persistir hilos: `SqliteSaver` o `PostgresSaver`.
- La memoria de largo plazo son archivos JSON (un solo proceso). Para multiusuario real: base de datos.
- Las pruebas automáticas usan un LLM guionado: validan el cableado y las reglas, no la calidad del texto de Gemini.
- Vegano se infiere de vegetariano + sin lácteos/huevo (la carta no tiene ese campo).
- El SDK `google-generativeai` usado por `langchain-google-genai` está deprecado (ver informe EP1).

## Declaración de uso de IA

Se utilizó Inteligencia Artificial Generativa (asistente LLM) durante el desarrollo de la EP2 como herramienta de apoyo para:

- **Estructuración y Arquitectura:** Diseño de flujos en LangGraph, articulación del patrón ReAct y definición del prompt dinámico con inyección de estado.
- **Codificación:** Generación del código base para las 9 herramientas (`src/herramientas.py`), refactorización del planificador determinista (`src/planificador.py`) y manejo de memoria en `src/memoria.py`.
- **Pruebas Unitarias y Cobertura:** Creación de mocks para las pruebas con `pytest` (sin requerir conexión ni API key) y elaboración del script de simulación (`scripts/demo_escenarios.py`).
- **Documentación y Redacción:** Apoyo en el formato Markdown del `README.md` y sintetización de la documentación técnica en `docs/`.

**Supervisión e Integración Humana:** Todo el código generado por IA fue revisado, depurado y validado manualmente. La regla de seguridad determinista (filtrado de alérgenos y dietas en código mediante `src/menu_repo.py`), las restricciones de negocio y la batería de pruebas fueron probadas e integradas bajo estricto criterio y responsabilidad de los desarrolladores.
## Referencias

- LangChain. (s.f.). *LangGraph documentation*. https://langchain-ai.github.io/langgraph/
- LangChain. (s.f.). *LangChain documentation*. https://python.langchain.com/
- Google. (2026). *Gemini API documentation*. https://ai.google.dev/gemini-api/docs
- Hugging Face. (s.f.). *sentence-transformers/all-MiniLM-L6-v2*. https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- Johnson, J., Douze, M., & Jégou, H. (2019). Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data, 7*(3), 535–547.
- Open-Meteo. (s.f.). *Open-Meteo API documentation*. https://open-meteo.com/en/docs
- Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. *ICLR 2023*. https://arxiv.org/abs/2210.03629
