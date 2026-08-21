#!/usr/bin/env python3
"""Pide a Google permiso para que EvA envíe correo, **una sola vez**.

    python obtener_permiso_gmail.py

Al terminar imprime el «testigo de refresco», que es lo que hay que guardar.
Ese testigo no caduca solo: sirve hasta que se revoque el permiso desde la
cuenta de Google, así que este script no hay que volver a ejecutarlo.

Antes hay que crear las credenciales en Google Cloud (una vez):

  1. https://console.cloud.google.com/  ->  crear un proyecto.
  2. «APIs y servicios» -> «Biblioteca» -> buscar **Gmail API** -> Habilitar.
  3. «Pantalla de consentimiento OAuth»: tipo **Externo**, poner un nombre y
     el correo de contacto. En «Usuarios de prueba» añadir la cuenta desde la
     que enviará EvA. Con dejarla en modo «Prueba» basta: los testigos de las
     apps en prueba caducan a los 7 días, así que conviene **Publicarla**
     (botón «Publicar aplicación») para que el permiso dure indefinidamente.
  4. «Credenciales» -> «Crear credenciales» -> «ID de cliente de OAuth» ->
     tipo **Aplicación de escritorio**. Salen un ID y un secreto de cliente.

El ámbito que se pide es solo el de **enviar** (`gmail.send`): esto no puede
leer el buzón ni borrar nada.
"""
from __future__ import annotations

import http.server
import json
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "client"))

from avcars.correo import GMAIL_SCOPE, GMAIL_TOKEN_URL  # noqa: E402

AUTORIZAR_URL = "https://accounts.google.com/o/oauth2/v2/auth"
PUERTO = 8765
REDIRECCION = f"http://localhost:{PUERTO}/"

#: Lo que Google devuelve al navegador tras aceptar. Se guarda aquí porque el
#: servidorcito corre en otro hilo.
_recibido: dict[str, str] = {}


class _Recogida(http.server.BaseHTTPRequestHandler):
    """Escucha una única vez para recoger el código que manda Google."""

    def do_GET(self):  # noqa: N802 — nombre impuesto por la librería
        _recibido.update(
            {
                k: v[0]
                for k, v in urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query
                ).items()
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        bien = "code" in _recibido
        self.wfile.write(
            (
                "<html><body style='font-family:sans-serif;text-align:center;"
                "margin-top:4em'><h2>"
                + ("Listo. Ya puedes cerrar esta pestaña." if bien else "No se pudo.")
                + "</h2><p>Vuelve a la ventana de la consola.</p></body></html>"
            ).encode("utf-8")
        )

    def log_message(self, *_):
        """Sin ruido: el navegador pide también el favicon y no interesa."""


def _del_json_de_google(path: Path) -> tuple[str, str]:
    """Saca ID y secreto del fichero que se descarga de Google Cloud.

    Lo guardan anidado bajo «installed» (apps de escritorio) o «web».
    """
    datos = json.loads(path.read_text(encoding="utf-8"))
    dentro = datos.get("installed") or datos.get("web") or datos
    return str(dentro.get("client_id", "")).strip(), str(
        dentro.get("client_secret", "")
    ).strip()


def _buscar_json_descargado() -> Path | None:
    """Google lo llama `client_secret_….json`. Se mira aquí y en Descargas."""
    candidatos: list[Path] = []
    for carpeta in (RAIZ, Path.home() / "Downloads", Path.home() / "Descargas"):
        try:
            candidatos.extend(carpeta.glob("client_secret*.json"))
        except OSError:
            continue
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def main() -> int:
    print("Permiso de Gmail para EvA")
    print("=========================\n")

    client_id = client_secret = ""

    # Si se pasa el fichero de Google (o se encuentra solo), nada de copiar
    # y pegar credenciales largas: de ahí salen la mitad de los errores.
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else _buscar_json_descargado()

    if path and path.exists():
        try:
            client_id, client_secret = _del_json_de_google(path)
        except (OSError, ValueError, AttributeError):
            print(f"No se pudo leer {path.name}; se piden a mano.\n")
        else:
            print(f"Credenciales leídas de: {path.name}\n")

    if not client_id or not client_secret:
        print("Pega las credenciales del «ID de cliente de OAuth» que creaste")
        print("en Google Cloud (tipo «Aplicación de escritorio»).\n")
        client_id = input("ID de cliente     : ").strip()
        client_secret = input("Secreto de cliente: ").strip()

    if not client_id or not client_secret:
        print("\nHacen falta las dos cosas.")
        return 1

    estado = secrets.token_urlsafe(16)
    parametros = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECCION,
            "response_type": "code",
            "scope": GMAIL_SCOPE,
            # Sin esto Google no devuelve testigo de refresco la segunda vez
            # que se autoriza la misma app, y es justo lo que buscamos.
            "access_type": "offline",
            "prompt": "consent",
            "state": estado,
        }
    )

    servidor = http.server.HTTPServer(("localhost", PUERTO), _Recogida)
    #: Para poder rendirse en vez de quedarse colgado si nadie contesta.
    servidor.timeout = 1

    url = f"{AUTORIZAR_URL}?{parametros}"
    print("\nAbriendo el navegador para que des el permiso…")
    print("Si no se abre solo, entra a mano en:\n")
    print(f"  {url}\n")
    webbrowser.open(url)
    print("Esperando a que aceptes… (Ctrl+C para dejarlo)")

    # Se atiende **aquí**, no en otro hilo: el servidor tiene que seguir
    # escuchando hasta que Google redirija de vuelta. Cerrarlo antes deja al
    # navegador con un ERR_CONNECTION_REFUSED en las narices.
    #
    # Y en bucle porque el navegador pide también `/favicon.ico`, que
    # consumiría la única petición atendida y nos dejaría sin el código.
    limite = time.monotonic() + 300
    while not _recibido and time.monotonic() < limite:
        servidor.handle_request()

    servidor.server_close()

    if not _recibido:
        print("\n✗ Se agotó la espera sin respuesta de Google.")
        return 1

    if _recibido.get("state") != estado:
        print("\n✗ La respuesta no coincide con la petición. Repite el proceso.")
        return 1
    if "code" not in _recibido:
        print(f"\n✗ Google no dio permiso: {_recibido.get('error', 'sin detalle')}")
        return 1

    datos = urllib.parse.urlencode(
        {
            "code": _recibido["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECCION,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")

    peticion = urllib.request.Request(
        GMAIL_TOKEN_URL,
        method="POST",
        data=datos,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urllib.request.urlopen(peticion, timeout=25) as r:
            respuesta = json.loads(r.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — aquí interesa enseñar lo que sea
        detalle = getattr(exc, "read", lambda: b"")().decode("utf-8", "replace")
        print(f"\n✗ Google rechazó el intercambio: {detalle or exc}")
        return 1

    refresh = respuesta.get("refresh_token", "")
    if not refresh:
        print("\n✗ Google no mandó testigo de refresco.")
        print("  Suele pasar si ya habías autorizado antes. Retira el permiso en")
        print("  https://myaccount.google.com/permissions y vuelve a intentarlo.")
        return 1

    print("\n✓ Permiso concedido.\n")
    print("Guarda esto en `web/data/correo.json` (no se sube al repositorio):\n")
    print(
        json.dumps(
            {
                "transporte": "gmail",
                "usuario": client_id,
                "password": client_secret,
                "refresh_token": refresh,
                "remitente": "aviacionmsfs@gmail.com",
                "gestion": "aviacionmsfs@gmail.com",
            },
            indent=2,
        )
    )
    print("\nY en Render, las mismas cosas como variables de entorno:")
    print("  EVA_CORREO_TRANSPORTE=gmail")
    print("  EVA_SMTP_USER=<el ID de cliente>")
    print("  EVA_SMTP_PASSWORD=<el secreto de cliente>")
    print("  EVA_GMAIL_REFRESH_TOKEN=<el testigo de arriba>")
    print("  EVA_SMTP_FROM=aviacionmsfs@gmail.com")
    print("  EVA_CORREO_GESTION=aviacionmsfs@gmail.com")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
