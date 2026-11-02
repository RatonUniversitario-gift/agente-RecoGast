# Evidencia de pruebas

## Pruebas automáticas (`pytest`, 32 casos)

Se ejecutan **sin red ni API key**: usan embeddings deterministas falsos y un LLM guionado
(`tests/fakes.py`) que emite llamadas a herramientas predefinidas. Eso valida el cableado del grafo, la
memoria y las reglas, no la calidad del texto de Gemini. Resultado completo en `docs/evidencia_pytest.txt`.

| Archivo | Qué valida | Indicador |
|---|---|---|
| `test_menu_repo.py` | Normalización de texto libre, regla de alérgenos/dietas, lo desconocido no se asume seguro | IE1 |
| `test_herramientas.py` | Cada herramienta; *gates* de seguridad; rechazo de pedidos no aptos; clima caído | IE1 |
| `test_planificador.py` | Prioridades, presupuesto, clima, replanificación por alergia | IE5 |
| `test_memoria.py` | Persistencia entre sesiones, recuperación semántica por comensal, ventana | IE3, IE4 |
| `test_agente.py` | Grafo completo multi-turno: historial, estado en el prompt, replan, nueva sesión | IE3, IE5, IE7 |

## Demostración de escenarios (`python scripts/demo_escenarios.py`)

Salida real en `docs/evidencia_demo.txt`:

1. **Seguridad**: sin restricciones confirmadas no se planifica; un pedido con un plato no apto para celíacos se rechaza y no se escribe nada.
2. **Presupuesto**: sin tope → 3 etapas ($28.600); $20.000 → fondo + postre ($18.800, la entrada no cabe); $5.000 → sin propuesta viable y advertencia.
3. **Clima**: con 31 °C propone Salmón (neutro) y con 8 °C lo reemplaza por Curry (cálido) tras `consultar_clima(forzar=true)`.
4. **Alergia tardía**: tras declarar alergia al pescado se descarta el Salmón por “contiene Pescado” y se propone reemplazo.
5. **Largo plazo**: en una segunda visita el perfil vuelve cargado pero *sin confirmar*, y las notas se recuperan por similitud.

## Prueba con el LLM real (manual)

Requiere `GOOGLE_API_KEY`. Guion sugerido para la defensa:

```
python src/main.py --comensal ana --mesa 5
> soy celíaco y tengo 40 mil
> me gusta algo cítrico de entrada
> ahora también soy alérgico al pescado
> /eventos
> pido el menú que propones
```
