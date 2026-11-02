"""Fuente externa: clima actual vía Open-Meteo (sin API key)."""
import requests

# Códigos WMO de Open-Meteo
_CODIGOS_CLIMA = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado",
    3: "nublado", 45: "con niebla", 48: "con niebla escarchada",
    51: "con llovizna ligera", 53: "con llovizna moderada", 55: "con llovizna intensa",
    61: "con lluvia ligera", 63: "con lluvia moderada", 65: "con lluvia intensa",
    71: "con nieve ligera", 73: "con nieve moderada", 75: "con nieve intensa",
    80: "con chubascos ligeros", 81: "con chubascos moderados", 82: "con chubascos violentos",
    95: "con tormenta electrica",
}
_CODIGOS_LLUVIA_NIEVE = {51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95}


def categorizar_clima(temperatura: float, codigo: int) -> str:
    """Resume el clima en 'calor', 'frio' o 'templado' (insumo del planificador)."""
    if codigo in _CODIGOS_LLUVIA_NIEVE or temperatura <= 14:
        return "frio"
    if temperatura >= 24:
        return "calor"
    return "templado"


def obtener_clima_estructurado(latitud: float = -33.4489, longitud: float = -70.6693) -> dict:
    """Consulta Open-Meteo. Si falla, degrada con gracia: disponible=False."""
    try:
        respuesta = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitud, "longitude": longitud,
                "current": "temperature_2m,weather_code",
                "timezone": "America/Santiago",
            },
            timeout=5,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()["current"]
        temperatura, codigo = datos["temperature_2m"], datos["weather_code"]
        return {
            "disponible": True, "temperatura": temperatura, "codigo": codigo,
            "descripcion": _CODIGOS_CLIMA.get(codigo, "con condiciones variables"),
            "categoria": categorizar_clima(temperatura, codigo),
        }
    except (requests.RequestException, KeyError, ValueError):
        return {"disponible": False, "temperatura": None, "codigo": None,
                "descripcion": None, "categoria": None}


def obtener_clima_actual(latitud: float = -33.4489, longitud: float = -70.6693) -> str:
    """Versión en texto (EP1), conservada por compatibilidad."""
    d = obtener_clima_estructurado(latitud, longitud)
    if not d["disponible"]:
        return "Clima actual: no disponible (no considerar el clima en la recomendación)."
    return f"Clima actual en el restaurante: {d['temperatura']}°C, {d['descripcion']}."
