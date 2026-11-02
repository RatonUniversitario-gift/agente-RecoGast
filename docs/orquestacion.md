# Orquestación de componentes

## 1. Arquitectura general

```mermaid
flowchart TB
    U([Comensal · CLI]) --> M[main.py<br/>bucle de conversación]
    M -->|mensaje + thread_id| A

    subgraph AGENTE["Agente ReAct · LangGraph (agent.py)"]
        direction TB
        P["Prompt dinámico<br/>instrucciones + ESTADO de sesión<br/>+ ventana de mensajes"]
        L{{"LLM Gemini<br/>razona y elige herramienta"}}
        T["ToolNode<br/>ejecuta la herramienta"]
        P --> L
        L -- "tool_call" --> T
        T -- "resultado" --> P
        L -- "respuesta final" --> OUT([Respuesta])
    end
    A[create_react_agent] --- AGENTE

    subgraph HERR["Herramientas (herramientas.py)"]
        direction LR
        subgraph C["Consulta"]
            h1[buscar_menu]
            h2[consultar_clima]
            h3[recuperar_memoria]
        end
        subgraph R["Razonamiento"]
            h4[verificar_alergenos]
            h5[planificar_comida]
            h6[calcular_cuenta]
        end
        subgraph W["Escritura"]
            h7[registrar_restricciones]
            h8[guardar_nota]
            h9[registrar_pedido]
        end
    end
    T --> HERR

    subgraph DET["Lógica determinista (sin LLM)"]
        MR[menu_repo.py<br/>regla de alérgenos]
        PL[planificador.py<br/>prioridades · replan]
    end
    R --> DET
    W --> DET

    subgraph MEM["Memoria (memoria.py)"]
        CP["Corto plazo<br/>MemorySaver + ventana"]
        ES["Estado de sesión<br/>EstadoSesion"]
        LP["Largo plazo<br/>perfil · pedidos · notas"]
    end
    AGENTE <--> CP
    PL <--> ES
    ES -. inyectado cada turno .-> P
    h3 --> LP
    h7 --> LP
    h8 --> LP
    h9 --> LP

    subgraph DATOS["Fuentes de datos"]
        F1[("menu.json<br/>FAISS + MiniLM local")]
        F2[("Open-Meteo<br/>clima con caché TTL")]
        F3[("data/memoria/*.json<br/>+ índice FAISS de notas")]
    end
    h1 --> F1
    h2 --> F2
    LP --> F3
```

## 2. Flujo de trabajo (ejemplo con cambios a mitad de conversación)

```mermaid
sequenceDiagram
    actor C as Comensal
    participant A as Agente (LLM)
    participant T as Herramientas
    participant E as EstadoSesion

    C->>A: "Hola, soy celíaco, tengo 40 mil"
    A->>T: registrar_restricciones(dietas=[celíaco], presupuesto=40000)
    T->>E: actualiza + guarda perfil (largo plazo)
    A->>T: consultar_clima()
    T->>E: clima = calor
    A->>T: planificar_comida()
    T->>E: propuesta = entrada fresca + fondo + postre
    A-->>C: menú propuesto (sin gluten, fresco)
    C->>A: "Ah, también soy alérgico al pescado"
    A->>T: registrar_restricciones(alergias=[pescado])
    T->>E: REPLAN: descarta Salmón, propone reemplazo
    A-->>C: "Ajusté el plan: descarté el salmón"
    C->>A: "Pido eso"
    A->>T: calcular_cuenta(...) y registrar_pedido(...)
    T->>T: re-verifica seguridad, escribe pedido + nota
    A-->>C: confirmación
```

## 3. Planificación y replanificación

```mermaid
stateDiagram-v2
    [*] --> SinConfirmar
    SinConfirmar --> Confirmadas: registrar_restricciones
    Confirmadas --> ConPropuesta: planificar_comida
    ConPropuesta --> ConPropuesta: REPLAN (alergia nueva)
    ConPropuesta --> ConPropuesta: REPLAN (presupuesto)
    ConPropuesta --> ConPropuesta: REPLAN (cambio de clima)
    ConPropuesta --> Pedido: registrar_pedido (re-verifica)
    Pedido --> [*]
```

Prioridad de etapas: **fondo (P1) > entrada (P2) > postre (P3)**. Se recorren en ese orden y cada una
se incluye si su opción segura más barata cabe en el presupuesto restante; el orden de servicio es
entrada → fondo → postre. Ante un cambio, `aplicar_cambio` descarta lo inválido, repropone y deja
una línea `REPLAN` en la bitácora (`/eventos`).

## 4. Capas de memoria

| Capa | Mecanismo | Qué guarda | Duración |
|---|---|---|---|
| Corto plazo | `MemorySaver` (LangGraph) + `trim_messages` | Historial del hilo | Sesión |
| Estado de sesión | `EstadoSesion` inyectado en el system prompt | Restricciones, presupuesto, clima, propuesta, bitácora | Sesión |
| Largo plazo (contenido) | JSON en `data/memoria/` | Perfil, pedidos | Permanente |
| Largo plazo (semántica) | FAISS sobre notas (`recuperar_memoria`) | Gustos, ocasiones, comentarios | Permanente |

El estado de sesión es lo que mantiene la coherencia aunque la ventana de mensajes descarte turnos antiguos.
