"""Demostración de extremo a extremo con procesos reales y capturas del monitor.

Levanta el proveedor simulado (puerto 8202) y la API (puerto 8201) con uvicorn, crea órdenes, deja que ocurran
fallas, reintentos y webhooks firmados reales, toma capturas con Playwright y escribe docs/ejecucion-demo.md.

Uso:  python scripts/demo_capturas.py
Variables: PYTHON_SERVIDORES (Python con las dependencias de requirements.txt), PW_CHANNEL=msedge (opcional)
"""
import json
import os
import pathlib
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter

from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parents[1]
API, PROVEEDOR = "http://127.0.0.1:8201", "http://127.0.0.1:8202"
ORDENES = [
    ("Bodegas Arrayán Sur SpA", "Av. Ejemplo 1234, Santiago", "MANTENCION_PREVENTIVA", "MEDIA"),
    ("Comercial Maitén Ltda.", "Calle Demo 456, Providencia", "CLIMATIZACION", "ALTA"),
    ("Distribuidora Lenga S.A.", "Pasaje Prueba 78, Las Condes", "ELECTRICIDAD", "CRITICA"),
    ("Logística Peumo Alto SpA", "Av. Ficticia 900, Ñuñoa", "INSPECCION", "BAJA"),
    ("Alimentos Coigüe Ltda.", "Camino Demo 12, Maipú", "MANTENCION_CORRECTIVA", "ALTA"),
    ("Clínica Quillay S.A.", "Av. Ejemplo 55, Pudahuel", "CLIMATIZACION", "CRITICA"),
    ("Colegio Canelo Norte SpA", "Sin cobertura, Camino Rural s/n", "INSPECCION", "MEDIA"),
    ("Hotel Tralca Ltda.", "Calle Demo 321, San Bernardo", "MANTENCION_PREVENTIVA", "MEDIA"),
]


def llamar(metodo, url, datos=None, encabezados=None):
    cuerpo = json.dumps(datos).encode() if isinstance(datos, (dict, list)) else datos
    peticion = urllib.request.Request(url, data=cuerpo, method=metodo,
                                      headers=encabezados or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(peticion, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def esperar(url, segundos=40):
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"No respondió: {url}")


def esperar_estabilidad(segundos=30):
    """Espera a que no queden órdenes en tránsito (pendientes, enviadas o asignadas)."""
    limite = time.time() + segundos
    while time.time() < limite:
        _, resumen = llamar("GET", f"{API}/api/resumen")
        estados = resumen["por_estado"]
        if not estados.get("PENDIENTE") and not estados.get("ENVIADA") and not estados.get("ASIGNADA"):
            return
        time.sleep(0.5)


def main():
    python = os.environ.get("PYTHON_SERVIDORES", sys.executable)
    temporal = pathlib.Path(tempfile.mkdtemp(prefix="demo-integraciones-"))
    secreto = secrets.token_hex(16)  # secreto efímero de la demostración: no se guarda en ningún lado
    entorno = {**os.environ, "SECRETO_WEBHOOK": secreto, "PYTHONIOENCODING": "utf-8"}
    log_api = open(temporal / "api.log", "w", encoding="utf-8")
    proveedor = subprocess.Popen(
        [python, "-m", "uvicorn", "--factory", "proveedor_simulado.main:crear_proveedor", "--port", "8202", "--log-level", "warning"],
        cwd=RAIZ, env={**entorno, "TASA_FALLO": "0.3", "SEMILLA": "7", "RETRASO_WEBHOOK_S": "1.0",
                       "FALLOS_FORZADOS": "OT-0008:3"},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    api = subprocess.Popen(
        [python, "-m", "uvicorn", "--factory", "app.main:crear_app", "--port", "8201", "--log-level", "warning"],
        cwd=RAIZ, env={**entorno, "RUTA_BD": str(temporal / "demo.db"), "MAX_INTENTOS": "3", "ESPERA_BASE": "0.2",
                       "URL_PROVEEDOR": PROVEEDOR, "URL_WEBHOOK": f"{API}/webhooks/proveedor"},
        stdout=log_api, stderr=subprocess.STDOUT)
    try:
        esperar(f"{PROVEEDOR}/v1/salud")
        esperar(f"{API}/salud")
        for cliente, direccion, servicio, prioridad in ORDENES:
            llamar("POST", f"{API}/api/ordenes", {"cliente": cliente, "direccion": direccion, "servicio": servicio, "prioridad": prioridad})
        esperar_estabilidad()
        # Un operador reintenta a mano las órdenes que agotaron sus intentos por fallas transitorias.
        _, con_error = llamar("GET", f"{API}/api/ordenes?estado=ERROR_INTEGRACION&limite=50")
        reintentadas = [o["codigo"] for o in con_error["contenido"] if "503" in (o["ultimo_error"] or "")]
        for codigo in reintentadas:
            llamar("POST", f"{API}/api/ordenes/{codigo}/reintentar")
        esperar_estabilidad()
        # Un aviso con firma falsa, para mostrar el rechazo en el registro.
        cuerpo = json.dumps({"id_evento": "falso-000001", "tipo": "TRABAJO_COMPLETADO", "codigo_orden": "OT-0001", "referencia": "PRV-99999"}).encode()
        estado_falso, _ = llamar("POST", f"{API}/webhooks/proveedor", cuerpo,
                                 {"Content-Type": "application/json", "X-Marca-Tiempo": str(int(time.time())), "X-Firma": "0" * 64})
        time.sleep(2.5)  # deja que el monitor se actualice

        capturas = RAIZ / "docs" / "capturas"
        capturas.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            navegador = p.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
            pagina = navegador.new_page(viewport={"width": 1440, "height": 900})
            pagina.goto(API + "/")
            pagina.wait_for_selector("#tabla-ordenes code")
            pagina.screenshot(path=capturas / "01-monitor.png", full_page=True)
            movil = navegador.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            movil.goto(API + "/")
            movil.wait_for_selector("#tabla-ordenes code")
            movil.screenshot(path=capturas / "02-monitor-movil.png", full_page=True)
            try:
                docs = navegador.new_page(viewport={"width": 1280, "height": 900})
                docs.goto(API + "/docs")
                docs.wait_for_selector(".opblock-tag-section", timeout=15000)
                docs.screenshot(path=capturas / "03-documentacion-openapi.png", full_page=True)
            except Exception as e:  # Swagger UI carga recursos desde un CDN público
                print("No se pudo capturar /docs:", e)
            navegador.close()

        _, ordenes = llamar("GET", f"{API}/api/ordenes?limite=20")
        _, resumen = llamar("GET", f"{API}/api/resumen")
        _, eventos = llamar("GET", f"{API}/api/eventos?limite=200")
        log_api.flush()
        lineas_log = [l for l in (temporal / "api.log").read_text(encoding="utf-8").splitlines() if l.startswith("{")]
        conteo = Counter(e["tipo"] for e in eventos)
        filas = "\n".join(f"| {o['codigo']} | {o['cliente']} | {o['estado']} | {o['intentos']} | {o['referencia_externa'] or '—'} |"
                          for o in reversed(ordenes["contenido"]))
        documento = f"""# Ejecución de demostración con procesos reales

Generado por `scripts/demo_capturas.py` el {time.strftime('%Y-%m-%d %H:%M')}. La API (puerto 8201) y el proveedor **simulado** (puerto 8202) corrieron como procesos separados y se comunicaron por HTTP. El proveedor simulado falla a propósito con una probabilidad del 30 %, y además se forzaron 3 fallas seguidas para OT-0008, para mostrar los intentos agotados y el reintento manual. Como las órdenes se procesan en paralelo, el resto del resultado cambia en cada ejecución. Se usó un secreto de webhooks aleatorio, válido solo durante la ejecución.

## Resultado

| Orden | Cliente (ficticio) | Estado final | Intentos | Referencia del proveedor |
|---|---|---|---|---|
{filas}

**Resumen:** {resumen['total']} órdenes · {resumen['entregadas_al_proveedor']} entregadas al proveedor · {resumen['con_error']} con error de integración · {resumen['fallas_transitorias']} fallas transitorias reintentadas · tasa de éxito {resumen['tasa_exito']} % · promedio de {resumen['promedio_intentos']} intentos.

Órdenes que agotaron sus intentos por fallas transitorias y se reintentaron a mano: {', '.join(reintentadas) or 'ninguna'}. La orden con dirección «Sin cobertura» fue rechazada por el proveedor (error permanente) y no se reintenta.

El aviso con firma falsa fue rechazado con HTTP {estado_falso}.

## Eventos registrados

| Tipo | Cantidad |
|---|---|
""" + "\n".join(f"| {tipo} | {n} |" for tipo, n in sorted(conteo.items())) + f"""

## Muestra del registro JSON de la API

```json
""" + "\n".join(lineas_log[:12]) + """
```
"""
        (RAIZ / "docs" / "ejecucion-demo.md").write_text(documento, encoding="utf-8")
        print(documento)
    finally:
        api.terminate()
        proveedor.terminate()
        api.wait(timeout=10)
        proveedor.wait(timeout=10)
        log_api.close()


if __name__ == "__main__":
    main()
