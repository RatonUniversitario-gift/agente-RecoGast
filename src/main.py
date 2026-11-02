"""CLI del agente RecoGast.

Uso:  python src/main.py --comensal ana --mesa 5
Comandos: /plan  /perfil  /eventos  /salir
"""
import argparse
import json
import uuid
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from dotenv import load_dotenv

from agent import construir_agente
from contexto import Contexto
from planificador import describir_estado

load_dotenv()
BASE = Path(__file__).resolve().parent.parent


def _texto(contenido) -> str:
    if isinstance(contenido, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in contenido)
    return str(contenido)


def main():
    ap = argparse.ArgumentParser(description="Agente gastronómico RecoGast")
    ap.add_argument("--comensal", default="invitado", help="id del comensal (clave de la memoria de largo plazo)")
    ap.add_argument("--mesa", default=None)
    args = ap.parse_args()

    try:
        print("Inicializando base vectorial, memoria y agente...")
        ctx = Contexto.crear(args.comensal, BASE / "data" / "menu.json", BASE / "data" / "memoria")
        agente = construir_agente(ctx)
    except (FileNotFoundError, RuntimeError, ValueError) as err:
        print(f"No se pudo iniciar el agente: {err}")
        return

    config = {"configurable": {"thread_id": f"{args.comensal}-{uuid.uuid4().hex[:6]}"},
              "recursion_limit": 25,
              "max_concurrency": 1}
    perfil = ctx.memoria.perfil(args.comensal)
    print(f"Listo. Comensal: {args.comensal} (visita #{perfil['visitas']}). "
          "Comandos: /plan /perfil /eventos /salir\n")

    # Primer mensaje implícito: el agente abre la conversación y confirma restricciones.
    entrada = f"(El comensal acaba de sentarse{' en la mesa ' + args.mesa if args.mesa else ''}. Salúdalo.)"
    while True:
        if entrada is None:
            try:
                entrada = input("Comensal > ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not entrada:
                entrada = None
                continue
            if entrada.lower() in ("/salir", "salir", "exit", "quit"):
                break
            if entrada == "/plan":
                print(describir_estado(ctx.estado, ctx.carta) + "\n"); entrada = None; continue
            if entrada == "/perfil":
                print(json.dumps(ctx.memoria.perfil(args.comensal), ensure_ascii=False, indent=2) + "\n")
                entrada = None; continue
            if entrada == "/eventos":
                print("\n".join(ctx.estado.eventos) or "(sin eventos)"); print(); entrada = None; continue
        try:
            for chunk in agente.stream({"messages": [("user", entrada)]}, config, stream_mode="updates"):
                for nodo, upd in chunk.items():
                    for m in upd.get("messages", []):
                        if nodo == "agent" and getattr(m, "tool_calls", None):
                            for tc in m.tool_calls:
                                print(f"  [herramienta] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})")
                        elif nodo == "agent":
                            print(f"\nRecoGast > {_texto(m.content)}\n")
        except Exception as err:  # el servicio no debe caerse por un fallo puntual del LLM
            if "RESOURCE_EXHAUSTED" in str(err):
                print("Cuota de Gemini agotada para este modelo. Cambia GOOGLE_MODEL en .env o espera al reinicio diario.\n")
            else:
                print(f"Error procesando la solicitud: {err}\n")


if __name__ == "__main__":
    main()
