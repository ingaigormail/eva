"""Cartilla EvA — servidor web de evaluación de vuelos.

Carga los ficheros `.avlog.json` que graba el cliente EvA, los pasa por el
mismo motor de evaluación que se usa en local y presenta el resultado:
telemetría del vuelo, desglose criterio a criterio y veredicto.

El motor de evaluación **no se reimplementa aquí**: se importa de `avcars`.
Esa fue una decisión de arquitectura desde el principio, para que evaluar en
el ordenador del piloto y evaluar en el servidor den exactamente el mismo
resultado.

Arranque:

    python web/app.py

y abrir http://127.0.0.1:5000
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional

from flask import (
    Flask,
    abort,
    flash,
    get_flashed_messages,  # noqa: F401 — lo usan las plantillas
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# El cliente vive en client/ y es donde están el esquema y el motor.
RAIZ_REPO = Path(__file__).resolve().parent.parent
CLIENT_DIR = RAIZ_REPO / "client"
sys.path.insert(0, str(CLIENT_DIR))

from avcars.config import (  # noqa: E402
    get_profile,
    load_aircraft,
    load_airports,
    load_profiles,
)
from avcars.evaluation.data_quality import Quality  # noqa: E402
from avcars.evaluation.scoring import Verdict, evaluate_flight  # noqa: E402
from avcars.evaluation import reglas_info  # noqa: E402
from avcars.prefile import PrefileExtras, icao_fpl, vatsim_prefile_url  # noqa: E402
from avcars.schema import FlightLog, FlightPlanInfo, PilotInfo  # noqa: E402
from avcars import (  # noqa: E402
    correo as correo_eva,
    cuentas,
    estadisticas,
    planes as planes_guardados,
    restablecer,
    secreto,
    sesion_web,
    solicitudes,
)

try:
    from avcars import correo as correo_eva  # noqa: F401
except (ImportError, ModuleNotFoundError):
    from correo_dummy import (  # noqa: E402,F401
        CorreoNoConfigurado,
        CorreoNoEnviado,
        configurado,
        correo_de_gestion,
        enviar,
    )

    class correo_eva:  # noqa: F811
        CorreoNoConfigurado = CorreoNoConfigurado
        CorreoNoEnviado = CorreoNoEnviado
        configurado = staticmethod(configurado)
        correo_de_gestion = staticmethod(correo_de_gestion)
        enviar = staticmethod(enviar)

# Imports desde el paquete web (módulos locales)
WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from csv_reader import FStelemetryCSVReader  # noqa: E402
from avlog_reader import AvlogJsonReader  # noqa: E402
from auth import (  # noqa: E402
    AUTH_BLOQUEADA,
    AUTH_DESCONOCIDO,
    AUTH_OK,
    PERM_GESTIONAR_USUARIOS,
    autenticar,  # noqa: F401 — usado por tests y otras rutas
    autenticar_detallado,
    esta_activa,
    existe_usuario,  # noqa: F401
    login_requerido,
    permiso_requerido,
)
import importacion  # noqa: E402
from despacho_pesos import datos_para_plantilla  # noqa: E402
from security import setup_security_headers, sanitize_input  # noqa: E402
from flask_wtf.csrf import CSRFProtect  # noqa: E402

app = Flask(__name__)
# Nunca escrita en el código: entorno o `web/data/secret_key.txt` (ver secreto.py).
app.secret_key = secreto.clave_de_sesion()

# CSRF protection
csrf = CSRFProtect(app)

# Security headers
setup_security_headers(app)

# La cookie de sesión, lo más cerrada que permita el sitio donde corra.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Con HTTPS delante (lo normal en un servidor público) se pone
    # EVA_COOKIE_SECURE=1 y la cookie deja de viajar en claro. Activarlo sin
    # HTTPS impediría iniciar sesión, así que no se da por hecho.
    SESSION_COOKIE_SECURE=os.environ.get("EVA_COOKIE_SECURE", "").strip() == "1",
)


@app.context_processor
def _identidad_en_plantillas():
    """Quién mira la página y si manda: la barra lateral lo necesita."""
    user_id = session.get("user_id", "")
    return {
        "usuario_actual": user_id,
        "usuario_es_admin": bool(user_id) and cuentas.es_admin(user_id),
    }


@app.before_request
def exigir_sesion():
    """Toda la cartilla y las APIs van con sesión. Login y estáticos, no."""
    # Públicas: quien aún no tiene cuenta debe poder pedirla, y quien la
    # tiene debe poder recuperar la contraseña sin haber entrado.
    if request.endpoint in (
        "static",
        "login_page",
        "logout",
        "solicitar_alta",
        "recuperar_password",
        "restablecer_password",
    ):
        return None
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login_page"))
    # Bloquear a alguien surte efecto ya: la sesión abierta deja de valer.
    if not esta_activa(user_id):
        session.pop("user_id", None)
        sesion_web.cerrar()
        return redirect(url_for("login_page"))
    return None

# Filtro personalizado para formatear números con separadores de miles
@app.template_filter("formato_numero")
def formato_numero(value, decimals=0):
    """Formatea un número con separadores de miles (comas)."""
    try:
        if decimals == 0:
            return f"{int(value):,}".replace(",", ".")
        else:
            return f"{float(value):.{int(decimals)}f}".replace(",", ".")
    except (ValueError, TypeError):
        return str(value)

PROFILES = load_profiles()
DEFAULT_PROFILE = "normal"
AIRCRAFT = load_aircraft()
AIRPORTS = load_airports()

#: Carpetas donde se buscan vuelos, en orden. La primera es la del propio
#: repositorio (útil en desarrollo); la segunda, donde el cliente instalado
#: deja las grabaciones.
SEARCH_DIRS = [
    CLIENT_DIR / "grabaciones",
    Path.home() / "EvA" / "grabaciones",
    Path.home() / "Documents" / "EvA" / "grabaciones",
]


# -- acceso a los vuelos ------------------------------------------------


def find_flights() -> list[Path]:
    """Todos los vuelos disponibles, del más reciente al más antiguo."""
    encontrados: list[Path] = []
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue
        encontrados.extend(directory.glob("*.avlog.json"))
        # En fixtures los ficheros de prueba no llevan el sufijo completo.
        if directory.name == "fixtures":
            encontrados.extend(directory.glob("*.json"))

    unicos = {p.resolve(): p for p in encontrados}.values()
    return sorted(unicos, key=lambda p: p.stat().st_mtime, reverse=True)


def piloto_actual() -> str:
    """El piloto de la sesión. Cadena vacía si no hay ninguno."""
    return str(session.get("user_id", "") or "")


def dueno_del_vuelo(path: Path) -> Optional[str]:
    """De quién es un vuelo, o None si no se puede saber.

    Se mira en dos sitios, por este orden:

    1. El propio fichero (`pilot.license_id`), que es la fuente de verdad.
    2. El registro de importaciones, para los `.csv` de fstelemetry, que no
       llevan datos de piloto: ahí consta quién lo subió.
    """
    if path.suffix == ".json" or path.name.endswith(".avlog.json"):
        vuelo = load_flight(path)
        if vuelo is not None:
            declarado = (vuelo.pilot.license_id or "").strip()
            if declarado:
                return declarado

    for huella, entrada in _registro_importaciones().items():  # noqa: B007
        if isinstance(entrada, dict) and entrada.get("fichero") == path.name:
            return str(entrada.get("piloto") or "") or None
    return None


def _registro_importaciones() -> dict:
    try:
        datos = json.loads(importacion.REGISTRO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def es_de(path: Path, piloto: str) -> bool:
    """True si ese vuelo se le puede enseñar a ese piloto.

    Un vuelo sin dueño averiguable **no se enseña a nadie**: es preferible
    que falte un vuelo antiguo en la cartilla a que un piloto vea los vuelos
    de otro. Para reclamarlo basta con volver a importarlo.
    """
    if not piloto:
        return False
    return dueno_del_vuelo(path) == piloto


def flights_of(piloto: str) -> list[Path]:
    """Los vuelos de un piloto, del más reciente al más antiguo."""
    return [p for p in find_flights() if es_de(p, piloto)]


def load_flight(path: Path) -> Optional[FlightLog]:
    """Carga un vuelo, o None si el fichero no es un log válido."""
    try:
        return FlightLog.model_validate(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError):
        return None


def _find_by_name(name: str) -> Optional[Path]:
    """Localiza un vuelo por nombre de fichero.

    Se busca entre los vuelos conocidos en vez de construir una ruta con lo
    que llega en la URL: así un nombre con `..` no puede sacar al servidor de
    sus carpetas.
    """
    for path in find_flights():
        if path.name == name:
            return path
    return None


# -- presentación -------------------------------------------------------


def telemetry(flight: FlightLog) -> dict:
    """Resumen de telemetría para la cabecera del informe."""
    track = flight.track
    summary = flight.summary

    altitudes = [p.alt_msl_ft for p in track] or [0]
    velocidades = [p.gs_kt for p in track] or [0]
    escoras = [abs(p.bank_deg) for p in track if p.bank_deg is not None] or [0]
    vs_descenso = [p.vs_fpm for p in track if p.vs_fpm < 0] or [0]

    en_vuelo = [p for p in track if not p.on_ground]

    return {
        "puntos": len(track),
        "eventos": len(flight.events),
        "duracion_min": summary.flight_time_min if summary else None,
        "distancia_nm": summary.total_distance_nm if summary else None,
        "combustible_kg": summary.fuel_used_kg if summary else None,
        "alt_max_ft": max(altitudes),
        "gs_max_kt": max(velocidades),
        "escora_max_deg": max(escoras),
        "vs_min_fpm": min(vs_descenso),
        "tiempo_en_vuelo_pct": (100 * len(en_vuelo) / len(track)) if track else 0,
        "avion": flight.flight_plan.aircraft_icao_type,
        "matricula": flight.flight_plan.aircraft_registration,
        "simulador": flight.client.simulator,
    }


def chart_points(flight: FlightLog, maximo: int = 240) -> dict:
    """Series para las gráficas, reducidas para no mandar miles de puntos."""
    track = flight.track
    if not track:
        return {"t": [], "alt": [], "gs": [], "lat": [], "lon": []}

    paso = max(1, len(track) // maximo)
    muestra = track[::paso]

    return {
        "t": [round(p.t / 60, 2) for p in muestra],  # minutos
        "alt": [p.alt_msl_ft for p in muestra],
        "gs": [p.gs_kt for p in muestra],
        "lat": [round(p.lat, 6) for p in muestra],
        "lon": [round(p.lon, 6) for p in muestra],
    }


def map_data(flight: FlightLog, verdict: Verdict) -> dict:
    """Datos para el mapa interactivo W1.

    Devuelve la ruta real del track, incidencias situadas en el espacio,
    eventos de despegue/aterrizaje, y coordenadas de aeropuertos.
    """
    track = flight.track
    if not track:
        return {}

    # Ruta real: muestreada a ~500 puntos para no saturar el navegador
    paso = max(1, len(track) // 500)
    route = [
        {
            "lat": round(p.lat, 6),
            "lon": round(p.lon, 6),
            "alt": int(p.alt_msl_ft),
            "gs": int(p.gs_kt),
            "t": round(p.t / 60, 1),
        }
        for p in track[::paso]
    ]

    # Incidencias del veredicto con posición (todos: pasados y fallados)
    incidents = []
    for item in verdict.items:
        if item.lat is not None and item.lon is not None:
            incidents.append(
                {
                    "rule": item.rule,
                    "detail": item.detail,
                    "lat": round(item.lat, 6),
                    "lon": round(item.lon, 6),
                    "passed": item.passed,
                }
            )

    # Eventos mapeados al track (despegue, touchdown, pausas…)
    events = []
    for ev in flight.events:
        pos = None
        if ev.position_pct is not None and track:
            idx = min(int(ev.position_pct * len(track)), len(track) - 1)
            pt = track[idx]
            pos = {"lat": round(pt.lat, 6), "lon": round(pt.lon, 6)}
        events.append(
            {
                "type": ev.type,
                "airport": ev.airport_icao,
                "runway": ev.runway,
                "pos": pos,
            }
        )

    # Aeropuertos de salida y llegada (coordenadas reales)
    airports = {}
    dep = flight.flight_plan.departure_icao.upper()
    arr = flight.flight_plan.arrival_icao.upper()
    if dep in AIRPORTS:
        a = AIRPORTS[dep]
        airports["departure"] = {"icao": dep, "lat": a.get("lat"), "lon": a.get("lon")}
    if arr in AIRPORTS:
        a = AIRPORTS[arr]
        airports["arrival"] = {"icao": arr, "lat": a.get("lat"), "lon": a.get("lon")}

    # Bounds para centrar el mapa automáticamente
    lats = [p.lat for p in track]
    lons = [p.lon for p in track]

    return {
        "route": route,
        "incidents": incidents,
        "events": events,
        "airports": airports,
        "bounds": {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons),
        },
    }


def planned_route_points(flight: FlightLog) -> list[dict]:
    """Extrae la ruta planificada del FPL como lista de waypoints con coordenadas.

    Parsea la cadena route (p.ej. "DCT LEVD DCT LEMD") y resuelve los
    ICAO codes contra AIRPORTS. Los puntos intermedios no resueltos se omiten.
    """
    fp = flight.flight_plan
    route_str = (fp.route or "").strip()
    if not route_str:
        return []

    # Aeropuertos de salida/llegada siempre presentes
    waypoints = []
    dep = fp.departure_icao.upper()
    arr = fp.arrival_icao.upper()
    if dep in AIRPORTS:
        a = AIRPORTS[dep]
        waypoints.append({"icao": dep, "lat": a["lat"], "lon": a["lon"]})

    # Parsear tokens de la ruta: ignorar DCT, N, N0xx, Fxxx, / y vacíos
    import re
    tokens = route_str.split()
    for tok in tokens:
        tok_up = tok.upper()
        if tok_up in ("DCT", "N") or re.match(r'^[NF]\d', tok_up) or re.match(r'^/', tok):
            continue
        # Intentar resolver como ICAO (4 letras)
        if re.match(r'^[A-Z]{4}$', tok_up) and tok_up in AIRPORTS:
            a = AIRPORTS[tok_up]
            waypoints.append({"icao": tok_up, "lat": a["lat"], "lon": a["lon"]})

    if arr in AIRPORTS:
        a = AIRPORTS[arr]
        # Evitar duplicado si el último waypoint ya es la llegada
        if not waypoints or waypoints[-1]["icao"] != arr:
            waypoints.append({"icao": arr, "lat": a["lat"], "lon": a["lon"]})

    return waypoints


# -- Autenticación (Login) -----------------------------------------------


@app.route("/login", methods=["GET", "POST"])
def login_page():
    """Login EvA. Solo usuarios dados de alta (fichero persistente)."""
    error = None
    sugerir_alta = False
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        password = request.form.get("password", "")

        if not user_id or not password:
            error = "ID de piloto y contraseña son obligatorios"
        else:
            resultado = autenticar_detallado(user_id, password)
            if resultado == AUTH_OK:
                # El ID tal como se dio de alta, no como lo tecleó el piloto:
                # `eva18l` y `EvA18L` son el mismo, y lo que se compare
                # después (sus vuelos) tiene que casar.
                user_id = cuentas.id_canonico(user_id) or user_id
                session["user_id"] = user_id
                # EVA Dispatcher arranca con la identidad validada aquí: la
                # cookie no la puede leer, así que se le deja anotada.
                sesion_web.abrir(user_id)
                # Se entra por la home de la aerolínea: lo primero que ve el
                # piloto es cómo va la aerolínea, no su propia lista de vuelos.
                return redirect(url_for("aerolinea"))
            if resultado == AUTH_DESCONOCIDO:
                error = "Ese ID de piloto no está dado de alta en EvA."
                sugerir_alta = True
            elif resultado == AUTH_BLOQUEADA:
                error = "Cuenta bloqueada. Contacta con un administrador."
            else:
                error = "Contraseña incorrecta"

    return render_template("login.html", error=error, sugerir_alta=sugerir_alta)


@app.route("/logout")
def logout():
    """Cierra la sesión y redirige al login."""
    session.pop("user_id", None)
    sesion_web.cerrar()
    return redirect(url_for("login_page"))


# -- Alta: se solicita, no se autoconcede --------------------------------


@app.route("/solicitar-alta", methods=["GET", "POST"])
def solicitar_alta():
    """Manda al responsable la petición de alta. **No crea ninguna cuenta.**"""
    datos = {"license_id": "", "nombre": "", "discord": "", "correo": ""}
    error = None
    enviado = False
    aviso_correo = None

    if request.method == "POST":
        for campo in datos:
            valor = request.form.get(campo, "").strip()
            # Sanitizar entrada: remove HTML, escape special chars
            datos[campo] = sanitize_input(valor)

        if not datos["license_id"]:
            error = "Indica tu Callsign o ID de EVA."
        elif not datos["nombre"]:
            error = "Indica tu nombre y apellidos."
        elif not cuentas.correo_valido(datos["correo"]):
            error = "Indica un correo electrónico válido donde avisarte."
        elif cuentas.existe_usuario(datos["license_id"]):
            # Ya tiene cuenta: lo suyo no es un alta, es recuperar el acceso.
            error = (
                "Ese ID ya está dado de alta. Si no recuerdas la contraseña, "
                "usa «He olvidado mi contraseña»."
            )
        else:
            # Se guarda ANTES de enviar: si el correo falla, la solicitud no
            # se pierde y el administrador la ve igual en la gestión.
            try:
                solicitudes.crear(
                    datos["license_id"],
                    datos["nombre"],
                    datos["correo"],
                    discord=datos["discord"],
                )
            except ValueError as exc:
                error = str(exc)

        if request.method == "POST" and not error:
            momento = datetime.now(timezone.utc).astimezone()
            cuerpo = (
                "Solicitud de alta en EvA\n"
                "========================\n\n"
                f"Callsign / ID de EVA : {datos['license_id']}\n"
                f"Nombre y apellidos   : {datos['nombre']}\n"
                f"Nombre en Discord    : {datos['discord'] or '(no indicado)'}\n"
                f"Correo de contacto   : {datos['correo']}\n"
                f"Fecha y hora         : {momento.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n"
                "La cuenta NO se ha creado: queda pendiente en la gestión de "
                "usuarios de EvA, que es donde se aprueba.\n"
            )
            # La solicitud ya está guardada; el correo es solo el aviso.
            enviado = True
            try:
                correo_eva.enviar(
                    correo_eva.correo_de_gestion(),
                    f"[EvA] Solicitud de alta — {datos['license_id']}",
                    cuerpo,
                )
            except (correo_eva.CorreoNoConfigurado, correo_eva.CorreoNoEnviado) as exc:
                app.logger.warning("Aviso de solicitud no enviado: %s", exc)
                aviso_correo = (
                    "Tu solicitud ha quedado registrada, pero el aviso por "
                    "correo al responsable no ha salido. Si no te contestan en "
                    "unos días, escríbeles por otro medio."
                )

    return render_template(
        "solicitar_alta.html",
        datos=datos,
        error=error,
        enviado=enviado,
        aviso_correo=aviso_correo,
    )


# -- Recuperación de contraseña ------------------------------------------

# Respuesta única: no revela si la cuenta existe.
_AVISO_RECUPERACION = (
    "Si esa cuenta existe y tiene un correo asociado, te hemos enviado un "
    "enlace para establecer una contraseña nueva. Caduca en "
    f"{restablecer.MINUTOS_VALIDEZ} minutos."
)


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar_password():
    """Envía un enlace de un solo uso. Nunca muestra la contraseña actual."""
    error = None
    aviso = None
    identificador = ""

    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        if not identificador:
            error = "Indica tu ID de piloto o tu correo."
        elif not correo_eva.configurado():
            error = (
                "El envío de correo no está configurado en este servidor, "
                "así que no se ha enviado nada. Avisa al responsable de EvA."
            )
        else:
            license_id = (
                identificador
                if cuentas.existe_usuario(identificador)
                else cuentas.buscar_por_correo(identificador)
            )
            destino = cuentas.correo_de(license_id) if license_id else ""
            if license_id and destino:
                testigo = restablecer.crear(license_id)
                enlace = url_for(
                    "restablecer_password", testigo=testigo, _external=True
                )
                try:
                    correo_eva.enviar(
                        destino,
                        "[EvA] Restablecer tu contraseña",
                        (
                            f"Hola {license_id}:\n\n"
                            "Alguien ha pedido restablecer la contraseña de tu "
                            "cuenta de EvA. Si has sido tú, abre este enlace:\n\n"
                            f"{enlace}\n\n"
                            f"Caduca en {restablecer.MINUTOS_VALIDEZ} minutos y "
                            "solo sirve una vez. Al usarlo, tu contraseña "
                            "anterior deja de valer.\n\n"
                            "Si no has sido tú, ignora este correo: no cambia "
                            "nada hasta que se use el enlace.\n"
                        ),
                    )
                except (correo_eva.CorreoNoConfigurado, correo_eva.CorreoNoEnviado) as exc:
                    app.logger.warning("Recuperación no enviada: %s", exc)
            aviso = _AVISO_RECUPERACION

    return render_template(
        "recuperar.html", error=error, aviso=aviso, identificador=identificador
    )


@app.route("/restablecer/<testigo>", methods=["GET", "POST"])
def restablecer_password(testigo: str):
    """Fija la contraseña nueva y quema el testigo."""
    error = None
    hecho = False
    valido = restablecer.piloto_de(testigo) is not None

    if request.method == "POST" and valido:
        password = request.form.get("password", "")
        repetida = request.form.get("password2", "")
        if len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif password != repetida:
            error = "Las dos contraseñas no coinciden."
        elif restablecer.consumir(testigo, password) is None:
            valido = False
        else:
            hecho = True

    return render_template(
        "restablecer.html", error=error, hecho=hecho, valido=valido, testigo=testigo
    )


# -- Gestión de usuarios (solo con permiso) -------------------------------

# Un alta recién creada da más margen que un olvido de contraseña: el piloto
# puede tardar en mirar el correo.
HORAS_ENLACE_ALTA = 24


def _enviar_enlace_de_contraseña(license_id: str, *, alta: bool) -> str:
    """Manda el enlace para que el piloto ponga su contraseña.

    Devuelve "" si salió, o el motivo por el que no. Reutiliza el mismo
    testigo de un solo uso que la recuperación: no hay dos mecanismos.
    """
    destino = cuentas.correo_de(license_id)
    if not destino:
        return f"{license_id} no tiene correo asociado: ponle uno y reenvíalo."
    if not correo_eva.configurado():
        return (
            "El envío de correo no está configurado en este servidor, así que "
            "no se ha enviado el enlace."
        )

    testigo = restablecer.crear(license_id, minutos=HORAS_ENLACE_ALTA * 60)
    enlace = url_for("restablecer_password", testigo=testigo, _external=True)
    cabecera = (
        "Ya tienes cuenta en EvA." if alta else "Se ha reiniciado tu contraseña."
    )
    try:
        correo_eva.enviar(
            destino,
            "[EvA] Tu cuenta: pon tu contraseña",
            (
                f"Hola {license_id}:\n\n"
                f"{cabecera} Para entrar, elige tu contraseña aquí:\n\n"
                f"{enlace}\n\n"
                f"El enlace caduca en {HORAS_ENLACE_ALTA} horas y solo sirve "
                "una vez. Hasta que lo uses, no puedes iniciar sesión.\n"
            ),
        )
    except (correo_eva.CorreoNoConfigurado, correo_eva.CorreoNoEnviado) as exc:
        app.logger.warning("Enlace de contraseña no enviado: %s", exc)
        return f"La cuenta está lista, pero el correo no salió: {exc}"
    return ""


@app.route("/gestion/usuarios")
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_usuarios():
    return render_template(
        "gestion_usuarios.html",
        usuarios=cuentas.listar_usuarios(),
        solicitudes=solicitudes.pendientes(),
        correo_listo=correo_eva.configurado(),
        correo_gestion=correo_eva.correo_de_gestion(),
    )


@app.route("/gestion/solicitudes/<int:solicitud_id>", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_solicitud(solicitud_id: int):
    """Aprobar una solicitud (crea la cuenta) o rechazarla. Nunca se borra."""
    accion = request.form.get("accion", "")
    yo = session.get("user_id", "")

    peticion = solicitudes.obtener(solicitud_id)
    if peticion is None or peticion["estado"] != solicitudes.PENDIENTE:
        flash("Esa solicitud ya no está pendiente.", "error")
        return redirect(url_for("gestion_usuarios"))

    if accion == "rechazar":
        solicitudes.resolver(solicitud_id, solicitudes.RECHAZADA, por=yo)
        flash(
            f"Solicitud de {peticion['license_id']} rechazada. No se le avisa: "
            "díselo tú si procede.",
            "aviso",
        )
        return redirect(url_for("gestion_usuarios"))

    if accion != "aprobar":
        flash("Acción desconocida.", "error")
        return redirect(url_for("gestion_usuarios"))

    try:
        cuentas.crear_cuenta(
            peticion["license_id"],
            secrets.token_urlsafe(24),
            peticion["correo"],
            rol=request.form.get("rol", cuentas.ROL_PILOTO),
        )
    except ValueError as exc:
        # La solicitud sigue pendiente: el administrador arregla y reintenta.
        flash(f"No se ha podido dar de alta a {peticion['license_id']}: {exc}", "error")
        return redirect(url_for("gestion_usuarios"))

    solicitudes.resolver(solicitud_id, solicitudes.APROBADA, por=yo)
    problema = _enviar_enlace_de_contraseña(peticion["license_id"], alta=True)
    if problema:
        flash(f"{peticion['license_id']} está dado de alta. {problema}", "aviso")
    else:
        flash(
            f"{peticion['license_id']} está dado de alta y ya tiene en su correo "
            "el enlace para poner su contraseña.",
            "exito",
        )
    return redirect(url_for("gestion_usuarios"))


@app.route("/gestion/usuarios/alta", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_alta():
    """Da de alta a quien lo solicitó. La contraseña la pone el piloto."""
    license_id = request.form.get("license_id", "").strip()
    correo_nuevo = request.form.get("correo", "").strip()
    rol = request.form.get("rol", cuentas.ROL_PILOTO)

    try:
        # Una contraseña que nadie conoce: la cuenta no sirve hasta que el
        # piloto ponga la suya con el enlace.
        cuentas.crear_cuenta(
            license_id, secrets.token_urlsafe(24), correo_nuevo, rol=rol
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("gestion_usuarios"))

    problema = _enviar_enlace_de_contraseña(license_id, alta=True)
    if problema:
        flash(f"{license_id} está dado de alta. {problema}", "aviso")
    else:
        flash(
            f"{license_id} está dado de alta y ya tiene en su correo el enlace "
            "para poner su contraseña.",
            "exito",
        )
    return redirect(url_for("gestion_usuarios"))


@app.route("/gestion/usuarios/<license_id>", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_accion(license_id: str):
    """Bloquear, desbloquear, cambiar rol o correo, reenviar el enlace."""
    accion = request.form.get("accion", "")
    yo = session.get("user_id", "")

    if not cuentas.existe_usuario(license_id):
        flash(f"{license_id} no está dado de alta.", "error")
        return redirect(url_for("gestion_usuarios"))

    # Dos maneras de quedarse sin poder administrar nada; las dos, cerradas.
    ultimo_admin = (
        cuentas.rol_de(license_id) == cuentas.ROL_ADMIN
        and cuentas.esta_activa(license_id)
        and cuentas.cuantos_admins() <= 1
    )

    try:
        if accion == "bloquear":
            if license_id == yo:
                flash("No puedes bloquearte a ti mismo.", "error")
            elif ultimo_admin:
                flash(
                    "Es el único administrador activo: nombra otro antes de "
                    "bloquearlo.",
                    "error",
                )
            else:
                cuentas.bloquear(license_id)
                flash(f"{license_id} queda bloqueado y no podrá entrar.", "exito")

        elif accion == "desbloquear":
            cuentas.desbloquear(license_id)
            flash(f"{license_id} vuelve a tener acceso.", "exito")

        elif accion == "rol":
            nuevo = request.form.get("rol", "")
            if nuevo != cuentas.ROL_ADMIN and ultimo_admin:
                flash(
                    "Es el único administrador activo: nombra otro antes de "
                    "quitarle el rol.",
                    "error",
                )
            else:
                cuentas.cambiar_rol(license_id, nuevo)
                flash(f"{license_id} pasa a ser {nuevo}.", "exito")

        elif accion == "correo":
            cuentas.cambiar_correo(license_id, request.form.get("correo", ""))
            flash(f"Correo de {license_id} actualizado.", "exito")

        elif accion == "enlace":
            problema = _enviar_enlace_de_contraseña(license_id, alta=False)
            if problema:
                flash(problema, "aviso")
            else:
                flash(f"Enlace enviado al correo de {license_id}.", "exito")

        else:
            flash("Acción desconocida.", "error")

    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("gestion_usuarios"))


# -- Gestión de vuelos (solo admin): subir por otro, o borrar cualquiera ---


@app.route("/gestion/vuelos")
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_vuelos():
    """Todos los vuelos de todos los pilotos. Solo administradores.

    Un piloto normal nunca ve esto: sigue viendo solo los suyos en `/vuelos`.
    """
    vuelos = []
    for path in find_flights():
        vuelos.append({
            "archivo": path.name,
            "piloto": dueno_del_vuelo(path) or "(sin dueño conocido)",
        })
    return render_template(
        "gestion_vuelos.html",
        vuelos=vuelos,
        pilotos=[u["license_id"] for u in cuentas.listar_usuarios()],
    )


@app.route("/gestion/vuelos/subir", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_subir_vuelo():
    """Sube un vuelo a la cartilla de OTRO piloto, elegido por el admin.

    Reutiliza la misma validación que la subida normal: si el fichero
    declara un dueño, tiene que ser justo el piloto elegido. Esto completa
    una cartilla que se quedó corta; no permite atribuirle a nadie el vuelo
    de otra persona.
    """
    destino = request.form.get("license_id", "").strip()
    file = request.files.get("file")

    if not destino or not cuentas.existe_usuario(destino):
        flash("Elige un piloto dado de alta.", "error")
        return redirect(url_for("gestion_vuelos"))
    if file is None or file.filename == "":
        flash("Elige un fichero.", "error")
        return redirect(url_for("gestion_vuelos"))

    ip_cliente = request.remote_addr or "desconocida"
    ok, mensaje, _codigo = _importar_vuelo(file.read(), file.filename, destino, ip_cliente)
    flash(
        f"{destino}: {mensaje}" if ok else f"No se pudo subir para {destino}: {mensaje}",
        "exito" if ok else "error",
    )
    return redirect(url_for("gestion_vuelos"))


@app.route("/gestion/vuelos/<nombre>/borrar", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_borrar_vuelo(nombre: str):
    """Borra un vuelo de la cartilla de quien sea. No se puede deshacer.

    Se busca entre los vuelos conocidos, igual que `detalle_registro`: así un
    nombre con `..` no puede borrar nada fuera de sitio.
    """
    path = _find_by_name(nombre)
    if path is None:
        flash(f"{nombre} no existe.", "error")
        return redirect(url_for("gestion_vuelos"))

    # No permitir borrar archivos de fixtures (son de prueba)
    if "fixtures" in path.parts:
        flash(f"{nombre} es un archivo de prueba, no se puede borrar.", "error")
        return redirect(url_for("gestion_vuelos"))

    huella = importacion.huella_de_fichero(nombre)
    try:
        path.unlink()
    except OSError as e:
        flash(f"No se pudo borrar {nombre}: {e}", "error")
        return redirect(url_for("gestion_vuelos"))

    if huella:
        importacion.olvidar(huella)
        estadisticas.borrar_por_huella(huella)

    flash(f"{nombre} borrado. Ya no cuenta en ninguna cartilla ni estadística.", "exito")
    return redirect(url_for("gestion_vuelos"))


# -- Gestión de pistas (solo admin): referencia para detectar la pista ----
# usada en cada vuelo, y así poder puntuar `runway_alignment_*` y
# `planned_runway_match` contra un dato real en vez de dejarlos sin evaluar.


def _rumbo_desde_designador(ident: str) -> Optional[float]:
    """«32L» -> 320.0, «07» -> 70.0. None si no se puede leer."""
    digitos = "".join(ch for ch in ident if ch.isdigit())
    if not digitos:
        return None
    try:
        return float(int(digitos) * 10)
    except ValueError:
        return None


@app.route("/gestion/pistas")
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_pistas():
    """Aeropuertos con ICAO real (LE.../GC...) sin pistas registradas.

    Sin esto, `runway_alignment_*` y `planned_runway_match` no se pueden
    evaluar en la mayoría de aeródromos pequeños: no hay con qué comparar
    el rumbo del avión al despegar o aterrizar.
    """
    with cuentas.conexion() as con:
        faltan = con.execute(
            """SELECT icao, name, municipality FROM aerodromos_es
               WHERE icao GLOB '[LG][ECG][A-Z][A-Z]' AND length(icao) = 4
                 AND type NOT IN ('heliport', 'balloonport', 'closed', 'seaplane_base')
                 AND type IS NOT NULL
                 AND name NOT LIKE '%HOSPITAL%' AND name NOT LIKE '%HELIPORT%'
                 AND name NOT LIKE '%HELIPAD%' AND name NOT LIKE '%HELIPUERTO%'
                 AND icao NOT IN (SELECT DISTINCT icao FROM pistas_es)
               ORDER BY icao"""
        ).fetchall()
    icao_precargado = request.args.get("icao", "").strip().upper()
    return render_template(
        "gestion_pistas.html",
        faltan=[dict(f) for f in faltan],
        icao_precargado=icao_precargado,
    )


@app.route("/gestion/pistas/guardar", methods=["POST"])
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_pistas_guardar():
    icao = sanitize_input(request.form.get("icao", ""), 4).strip().upper()
    pista_le = sanitize_input(request.form.get("pista_le", ""), 3).strip().upper()
    pista_he = sanitize_input(request.form.get("pista_he", ""), 3).strip().upper()
    preferente = sanitize_input(request.form.get("preferente", ""), 3).strip().upper()

    if not (icao and pista_le and pista_he):
        flash("Faltan campos: ICAO y las dos cabeceras de la pista.", "error")
        return redirect(url_for("gestion_pistas"))
    if preferente not in (pista_le, pista_he):
        flash(
            f"La pista preferente debe ser {pista_le} o {pista_he}, "
            f"tal como se han escrito.",
            "error",
        )
        return redirect(url_for("gestion_pistas", icao=icao))

    with cuentas.conexion() as con:
        existe = con.execute(
            "SELECT 1 FROM aerodromos_es WHERE icao = ?", (icao,)
        ).fetchone()
        if existe is None:
            # El aeropuerto ni siquiera constaba: se da de alta con lo mínimo.
            con.execute(
                "INSERT INTO aerodromos_es (icao, default_runway, sources) "
                "VALUES (?, ?, 'admin')",
                (icao, preferente),
            )
        else:
            con.execute(
                "UPDATE aerodromos_es SET default_runway = ? WHERE icao = ?",
                (preferente, icao),
            )

        # Un aeródromo pequeño solo tiene una pista física (dos cabeceras);
        # si ya había una fila para este ICAO, se sustituye en vez de
        # duplicar — el formulario describe la pista entera, no un extremo.
        con.execute("DELETE FROM pistas_es WHERE icao = ?", (icao,))
        con.execute(
            """INSERT INTO pistas_es
               (icao, designator, le_ident, le_heading, he_ident, he_heading)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                icao,
                f"{pista_le}/{pista_he}",
                pista_le,
                _rumbo_desde_designador(pista_le),
                pista_he,
                _rumbo_desde_designador(pista_he),
            ),
        )

    flash(f"{icao}: pista {pista_le}/{pista_he} guardada (preferente {preferente}).", "exito")
    return redirect(url_for("gestion_pistas"))


# -- Gestión de reglas de puntuación (solo admin, de solo lectura) --------


@app.route("/gestion/reglas")
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_reglas():
    """Las 26 reglas del motor de evaluación, con su trazabilidad exacta.

    Fuente única: `avcars.evaluation.reglas_info`. El alcance y qué reglas
    están bloqueadas se derivan en vivo del motor; solo las explicaciones
    en español están escritas a mano, y en un solo sitio.
    """
    return render_template("gestion_reglas.html", reglas=reglas_info.listar())


@app.route("/gestion/reglas/<regla_id>")
@permiso_requerido(PERM_GESTIONAR_USUARIOS)
def gestion_regla_detalle(regla_id: str):
    regla = reglas_info.obtener(regla_id)
    if regla is None:
        abort(404)
    return render_template("gestion_regla_detalle.html", r=regla)


def verdict_summary(verdict: Verdict) -> dict:
    """Traduce el veredicto a lo que necesita la plantilla."""
    quality = verdict.quality

    if not verdict.evaluable:
        titulo, clase = "NO EVALUABLE", "no-evaluable"
    elif verdict.passed:
        titulo, clase = "APTO", "apto"
    else:
        titulo, clase = "NO APTO", "no-apto"

    return {
        "titulo": titulo,
        "clase": clase,
        "score": verdict.score,
        "evaluable": verdict.evaluable,
        "quality": quality,
        "superados": [i for i in verdict.items if i.passed],
        "fallados": [i for i in verdict.items if not i.passed],
        "penalizacion": sum(i.points for i in verdict.items if not i.passed),
    }


# -- rutas ---------------------------------------------------------------


@app.route("/")
def index():
    vuelos = []
    for path in flights_of(piloto_actual()):
        flight = load_flight(path)
        if flight is None:
            continue
        vuelos.append(
            {
                "nombre": path.name,
                "callsign": flight.pilot.callsign or flight.pilot.license_id,
                "salida": flight.flight_plan.departure_icao,
                "llegada": flight.flight_plan.arrival_icao,
                "minutos": flight.summary.flight_time_min if flight.summary else None,
                "puntos": len(flight.track),
                "fecha": path.stat().st_mtime,
            }
        )

    carpetas = [str(d) for d in SEARCH_DIRS if d.exists()]
    return render_template("index.html", vuelos=vuelos, carpetas=carpetas, title="Cartilla EvA")


@app.route("/vuelo/<nombre>")
def detalle(nombre: str):
    path = _find_by_name(nombre)
    if path is None:
        abort(404)
    # 404 y no 403: a un piloto no se le confirma qué vuelos tienen los demás.
    if not es_de(path, piloto_actual()):
        abort(404)

    flight = load_flight(path)
    if flight is None:
        abort(404)

    perfil = request.args.get("perfil", DEFAULT_PROFILE)
    if perfil not in PROFILES:
        perfil = DEFAULT_PROFILE

    aeronave = AIRCRAFT.get(flight.flight_plan.aircraft_icao_type)
    verdict = evaluate_flight(flight, PROFILES[perfil], aircraft=aeronave)
    datos_veredicto = verdict_summary(verdict)
    datos_telemetria = telemetry(flight)
    datos_grafica = chart_points(flight)
    datos_mapa = map_data(flight, verdict)
    ruta_planificada = planned_route_points(flight)

    return render_template(
        "vuelo.html",
        flight=flight,
        nombre=nombre,
        veredicto=datos_veredicto,
        telemetria=datos_telemetria,
        graficas=datos_grafica,
        mapa=datos_mapa,
        ruta_planificada=ruta_planificada,
        perfil=perfil,
        perfiles=PROFILES.keys(),
        umbral=PROFILES[perfil]["pass_score"],
        fallos_automaticos=verdict.failed_hard,
        no_evaluados=verdict.not_evaluated,
    )


@app.route("/vuelo/<nombre>/json")
def crudo(nombre: str):
    path = _find_by_name(nombre)
    if path is None:
        abort(404)
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@app.route("/plan")
def plan():
    flota = [
        {"icao": icao, "nombre": data.get("nombre", icao)}
        for icao, data in AIRCRAFT.items()
    ]
    estelas = {
        icao: data["referencia_atc"]["estela"]
        for icao, data in AIRCRAFT.items()
        if "referencia_atc" in data and "estela" in data["referencia_atc"]
    }
    pesos = {
        icao: data["referencia_atc"]["mtow_kg"]
        for icao, data in AIRCRAFT.items()
        if "referencia_atc" in data and "mtow_kg" in data["referencia_atc"]
    }
    despacho = datos_para_plantilla(AIRCRAFT)

    # `/plan?plan=<id>` reabre un plan guardado. Si no es suyo, no se abre y
    # el planificador sale en blanco: no se confirma que exista.
    plan_guardado = None
    pedido = request.args.get("plan", "").strip()
    if pedido.isdigit():
        plan_guardado = planes_guardados.obtener(int(pedido), piloto_actual())

    return render_template(
        "plan.html",
        flota=flota,
        estelas=estelas,
        pesos=pesos,
        despacho=despacho,
        plan_guardado=plan_guardado,
    )


def _geo_para_mapa(top_aeropuertos: list, top_rutas: list) -> dict:
    """Lat/lon de aeropuertos y rutas que ya salen en los tops (AIRPORTS).

    No inventa vuelos: si un ICAO no está en airports.json, se omite.
    """
    puntos = []
    for a in top_aeropuertos:
        icao = (a.get("icao") or "").upper()
        info = AIRPORTS.get(icao) or {}
        lat, lon = info.get("lat"), info.get("lon")
        if lat is None or lon is None:
            continue
        puntos.append({
            "icao": icao,
            "lat": lat,
            "lon": lon,
            "operaciones": a.get("operaciones") or 0,
        })
    rutas = []
    for r in top_rutas:
        origen = (r.get("origen") or "").upper()
        destino = (r.get("destino") or "").upper()
        ao, ad = AIRPORTS.get(origen) or {}, AIRPORTS.get(destino) or {}
        if ao.get("lat") is None or ad.get("lat") is None:
            continue
        rutas.append({
            "origen": origen,
            "destino": destino,
            "vuelos": r.get("vuelos") or 0,
            "origen_lat": ao["lat"],
            "origen_lon": ao["lon"],
            "destino_lat": ad["lat"],
            "destino_lon": ad["lon"],
        })
    return {"puntos": puntos, "rutas": rutas}


@app.route("/aerolinea")
@login_requerido
def aerolinea():
    """Home de la aerolínea: estadísticas agregadas de todos los pilotos.

    Datos reales desde el primer día (tabla `vuelos_resumen`). El look es
    UI-04: tarjetas, gráfico mensual y mapa con intensidad de rutas ya
    listadas en los tops (coordenadas de airports.json).
    """
    top_rutas = estadisticas.top_rutas()
    top_aeropuertos = estadisticas.top_aeropuertos()
    return render_template(
        "aerolinea.html",
        kpis=estadisticas.kpis_globales(),
        top_actividad=estadisticas.top_pilotos_actividad(),
        top_calidad=estadisticas.top_pilotos_calidad(),
        minimo_calidad=estadisticas.MINIMO_VUELOS_RANKING_CALIDAD,
        top_rutas=top_rutas,
        top_aeropuertos=top_aeropuertos,
        mensual=estadisticas.actividad_mensual(),
        incidencias=estadisticas.incidencia_mas_frecuente(),
        mapa_flota=_geo_para_mapa(top_aeropuertos, top_rutas),
    )


#: Dónde se publica el instalador. Va en GitHub y no en el propio servidor a
#: propósito: son 53 MB por descarga, y el disco del VPS anda justo. GitHub no
#: cobra tráfico en repositorios públicos y además guarda las versiones.
DESCARGA_URL = os.environ.get(
    "EVA_DESCARGA_URL",
    "https://github.com/ingaigormail/eva/releases/latest/download/setup.exe",
)
DESCARGA_VERSION = os.environ.get("EVA_DESCARGA_VERSION", "Última versión")


@app.route("/descargar")
@login_requerido
def descargar():
    """De dónde se baja EvA Airliner y cómo se usa.

    En el servidor el botón VUELO no puede abrir el grabador — está en el PC
    del piloto, no aquí —, así que lleva a esta página.
    """
    return render_template(
        "descargar.html",
        enlace_descarga=DESCARGA_URL,
        version_visible=DESCARGA_VERSION,
    )


@app.route("/registro")
@login_requerido
def registro():
    """Registrar un vuelo: subir su fichero a la cartilla. **Solo eso.**

    Antes esta pantalla hacía dos cosas —subir y listar—, y por eso «Registro»
    y «Vuelos» se pisaban en la barra. La lista vive ahora en `/vuelos`.
    """
    return render_template("registro.html")


@app.route("/vuelos/<nombre>/borrar", methods=["POST"])
@login_requerido
def borrar_mi_vuelo(nombre: str):
    """Un piloto borra un vuelo **suyo**. Para cualquier otro, usa la gestión.

    Mismo blindaje que `detalle_registro`: se busca entre los vuelos
    conocidos, nunca se construye la ruta con lo que llega en la URL.
    """
    path = _find_by_name(nombre)
    if path is None or not es_de(path, piloto_actual()):
        # No se distingue «no existe» de «no es tuyo»: no hay por qué
        # confirmarle a nadie qué vuelos tienen los demás.
        abort(404)

    # No permitir borrar archivos de fixtures (son de prueba)
    if "fixtures" in path.parts:
        abort(403)

    huella = importacion.huella_de_fichero(nombre)
    try:
        path.unlink()
    except OSError as e:
        flash(f"No se pudo borrar {nombre}: {e}", "error")
        return redirect(url_for("vuelos"))

    if huella:
        importacion.olvidar(huella)
        estadisticas.borrar_por_huella(huella)

    flash(f"{nombre} borrado.", "exito")
    return redirect(url_for("vuelos"))


@app.route("/vuelos")
@login_requerido
def vuelos():
    """Los vuelos grabados de este piloto (CSV + AVLOG)."""
    vuelos = []
    piloto = piloto_actual()

    # Buscar archivos CSV y AVLOG en directorios
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue

        # Archivos CSV
        for csv_file in directory.glob("*.csv"):
            if not es_de(csv_file, piloto):
                continue
            try:
                puntos, summary = FStelemetryCSVReader.read_csv(csv_file)
                if summary and summary.points_recorded > 0:
                    vuelos.append({
                        "archivo": csv_file.name,
                        "fecha": csv_file.name,  # YYYYMMDDHHMMSS.csv
                        "duracion_min": round(summary.flight_time_min, 1),
                        "distancia_nm": round(summary.distance_nm, 1),
                        "alt_max_ft": int(summary.alt_max_ft),
                        "gs_max_kt": int(summary.gs_max_kt),
                        "puntos": summary.points_recorded,
                    })
            except Exception:
                continue

        # Archivos AVLOG
        for avlog_file in directory.glob("*.avlog.json"):
            if not es_de(avlog_file, piloto):
                continue
            try:
                points, summary = AvlogJsonReader.read_avlog(avlog_file)
                if summary and summary.points_recorded > 0:
                    vuelos.append({
                        "archivo": avlog_file.name,
                        "fecha": avlog_file.name,
                        "duracion_min": round(summary.flight_time_min, 1),
                        "distancia_nm": round(summary.distance_nm, 1),
                        "alt_max_ft": int(summary.alt_max_ft),
                        "gs_max_kt": int(summary.gs_max_kt),
                        "puntos": summary.points_recorded,
                    })
            except Exception:
                continue

    # Ordenar por fecha (más recientes primero)
    vuelos.sort(key=lambda v: v["fecha"], reverse=True)

    return render_template("vuelos.html", vuelos=vuelos, total=len(vuelos))


@app.route("/registro/<nombre>")
@login_requerido
def detalle_registro(nombre: str):
    """D3: Detalle de vuelo grabado (CSV o AVLOG)."""
    # Buscar el archivo
    archivo_path = None
    for directory in SEARCH_DIRS:
        if not directory.exists():
            continue
        candidate = directory / nombre
        if candidate.exists():
            archivo_path = candidate
            break

    if not archivo_path:
        abort(404)
    if not es_de(archivo_path, piloto_actual()):
        abort(404)

    # Determinar tipo y leer datos
    resumen = None
    graficas = {"t": [], "alt": [], "gs": [], "vs": []}

    if nombre.endswith(".csv"):
        try:
            puntos, summary = FStelemetryCSVReader.read_csv(archivo_path)
            if summary and summary.points_recorded > 0:
                resumen = summary
                # Datos para gráficas
                if puntos and len(puntos) > 0:
                    paso = max(1, len(puntos) // 200)
                    muestra = puntos[::paso]
                    graficas = {
                        "t": [round(p.timestamp / 60, 1) for p in muestra],
                        "alt": [int(p.alt_msl_ft) for p in muestra],
                        "gs": [int(p.gs_kt) for p in muestra],
                        "vs": [int(p.vs_fpm) for p in muestra],
                    }
        except Exception as e:
            print(f"Error leyendo CSV {archivo_path}: {e}")
            abort(404)
    else:
        # AVLOG
        try:
            points, summary = AvlogJsonReader.read_avlog(archivo_path)
            if summary and summary.points_recorded > 0:
                resumen = summary
                # Datos para gráficas (muestrear para no sobrecargar)
                if points:
                    paso = max(1, len(points) // 200)
                    muestra = points[::paso]
                    graficas = {
                        "t": [round(p.timestamp / 60, 1) for p in muestra],
                        "alt": [int(p.alt_msl_ft) for p in muestra],
                        "gs": [int(p.gs_kt) for p in muestra],
                        "vs": [int(p.vs_fpm) for p in muestra],
                    }
        except Exception as e:
            print(f"Error leyendo AVLOG {archivo_path}: {e}")
            abort(404)

    if resumen is None:
        abort(404)

    # El CSV de fstelemetry no lleva plan de vuelo, así que no hay origen ni
    # destino con los que comprobar una etapa. Solo aplica al AVLOG.
    etapa_vuelta = None
    if nombre.endswith(".avlog.json"):
        vuelo = load_flight(archivo_path)
        if vuelo is not None:
            etapa_vuelta = _etapa_de_vuelta_espana(
                vuelo.flight_plan.departure_icao, vuelo.flight_plan.arrival_icao
            )

    return render_template(
        "detalle_registro.html",
        nombre=nombre,
        resumen=resumen,
        graficas=graficas,
        etapa_vuelta=etapa_vuelta,
    )


# -- APIs -------------------------------------------------------


@app.route("/api/aeropuerto/<icao>")
def get_aeropuerto(icao: str):
    if icao.upper() not in AIRPORTS:
        abort(404)
    airport = AIRPORTS[icao.upper()]
    return jsonify({
        "icao": icao.upper(),
        "lat": airport.get("lat"),
        "lon": airport.get("lon"),
    })


# -- Lanzar EVA Airliner desde la web (solo en local) ---------------------

#: El grabador que hayamos lanzado, para no abrir dos.
_grabador: Optional[subprocess.Popen] = None

_LOOPBACK = ("127.0.0.1", "::1", "localhost")


def se_puede_lanzar_en_local() -> bool:
    """¿Puede este servidor arrancar programas de esta máquina?

    Un navegador no puede lanzar un `.exe`: lo prohíben por diseño, y menos mal.
    Pero mientras EvA corre en el PC del piloto, el servidor **es** esa máquina,
    así que puede hacerlo él.

    Dos cerrojos, porque una ruta que arranca procesos en un servidor público
    sería una puerta abierta de par en par:

    1. La petición viene de la propia máquina.
    2. El servidor está en modo desarrollo, o alguien lo ha permitido
       expresamente con `EVA_LANZAR_LOCAL=1`.

    Ojo con el punto 1 el día del despliegue: detrás de un proxy en el mismo
    host, **todas** las peticiones parecen locales. Por eso hace falta también
    el punto 2, que en producción no se cumple.
    """
    if os.environ.get("EVA_LANZAR_LOCAL", "").strip() == "0":
        return False
    permitido = app.debug or os.environ.get("EVA_LANZAR_LOCAL", "").strip() == "1"
    return permitido and (request.remote_addr or "") in _LOOPBACK


@app.context_processor
def _lanzar_en_plantillas():
    return {"puede_lanzar_vuelo": se_puede_lanzar_en_local()}


@app.route("/api/vuelo/lanzar", methods=["POST"])
@login_requerido
def lanzar_grabador():
    """Arranca EVA Airliner (D4) en esta máquina. Uno solo."""
    global _grabador

    if not se_puede_lanzar_en_local():
        return jsonify({
            "ok": False,
            "mensaje": "EVA Airliner se abre desde el escritorio: este "
                       "servidor no puede arrancar programas.",
        }), 403

    if _grabador is not None and _grabador.poll() is None:
        return jsonify({
            "ok": False,
            "mensaje": "EVA Airliner ya está abierto. Búscalo en la barra de "
                       "tareas: solo debe haber uno grabando.",
        }), 409

    try:
        _grabador = subprocess.Popen(
            [sys.executable, "-m", "client.avcars.gui"],
            cwd=str(RAIZ_REPO),
        )
    except OSError as e:
        app.logger.warning("No se pudo lanzar EVA Airliner: %s", e)
        return jsonify({"ok": False, "mensaje": f"No se pudo abrir: {e}"}), 500

    return jsonify({"ok": True, "mensaje": "EVA Airliner abriéndose…"}), 200


# -- Planes de vuelo guardados (D3) --------------------------------------


@app.route("/api/plan/guardar", methods=["POST"])
@login_requerido
def guardar_plan():
    """Guarda el plan del planificador. Del piloto de la sesión, de nadie más."""
    datos = request.get_json(silent=True) or {}
    plan_id = datos.pop("plan_id", None)
    via = datos.pop("via", "")
    try:
        ident = planes_guardados.guardar(
            piloto_actual(),
            datos,
            plan_id=int(plan_id) if plan_id else None,
            via=via,
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "mensaje": str(exc)}), 422
    return jsonify({"ok": True, "id": ident, "mensaje": "Plan guardado"}), 200


@app.route("/planes-de-vuelo")
@login_requerido
def planes_de_vuelo():
    """D3: los planes que ha guardado este piloto."""
    return render_template(
        "planes_de_vuelo.html", planes=planes_guardados.listar(piloto_actual())
    )


@app.route("/planes-de-vuelo/<int:plan_id>/borrar", methods=["POST"])
@login_requerido
def borrar_plan(plan_id: int):
    if not planes_guardados.borrar(plan_id, piloto_actual()):
        # Ni existe ni es suyo: no se distingue una cosa de la otra.
        abort(404)
    return redirect(url_for("planes_de_vuelo"))


@app.route("/api/plan/fpl", methods=["POST"])
def gen_fpl():
    data = request.get_json() or {}

    # Validación básica
    callsign = data.get("callsign", "").strip().upper()
    if not callsign:
        return jsonify({"error": "callsign requerido"}), 422

    departure = data.get("departure", "").strip().upper()
    arrival = data.get("arrival", "").strip().upper()

    # Validar que sean ICAO válidos (4 caracteres)
    if len(departure) != 4 or len(arrival) != 4:
        return jsonify({"error": "ICAO inválido"}), 422

    rules = (data.get("rules") or "VFR").strip().upper()
    aircraft = (data.get("aircraft") or "C172").strip()
    alternate = (data.get("alternate") or "").strip().upper()
    route = (data.get("route") or "").strip()
    cruise_speed = data.get("cruise_speed")
    departure_time_str = (data.get("departure_time") or "").strip()
    eet_minutes = data.get("eet_minutes")
    endurance_minutes = data.get("endurance_minutes")
    remarks = (data.get("remarks") or "").strip()
    flight_date_str = (data.get("flight_date") or "").strip()
    voice_capability = (data.get("voice_capability") or "V").strip()
    equipment = (data.get("equipment") or "S").strip()
    transponder = (data.get("transponder") or "C").strip()
    wake_turbulence = (data.get("wake_turbulence") or "L").strip()

    # Parsear hora y fecha
    from datetime import time, date
    departure_utc = None
    if departure_time_str:
        try:
            h, m = map(int, departure_time_str.split(":"))
            departure_utc = time(h, m)
        except ValueError:
            pass
    flight_date = None
    if flight_date_str:
        try:
            flight_date = date.fromisoformat(flight_date_str)
        except ValueError:
            pass

    flight_plan = FlightPlanInfo(
        rules=rules,
        departure_icao=departure,
        arrival_icao=arrival,
        alternate_icao=alternate if alternate else None,
        route=route if route else None,
        aircraft_icao_type=aircraft,
        network="VATSIM",
        atc_controlled=False,
    )
    pilot = PilotInfo(
        callsign=callsign,
        license_id=callsign,
    )
    extras = PrefileExtras(
        cruise_speed=cruise_speed,
        departure_utc=departure_utc,
        eet_minutes=eet_minutes,
        endurance_minutes=endurance_minutes,
        remarks=remarks if remarks else None,
        flight_date=flight_date,
        voice_capability=voice_capability,
        equipment=equipment,
        transponder=transponder,
        wake_turbulence=wake_turbulence,
    )

    fpl = icao_fpl(flight_plan, pilot, extras)

    return jsonify({"fpl": fpl})


@app.route("/api/plan/vatsim-url", methods=["POST"])
def get_vatsim_url():
    data = request.get_json() or {}

    callsign = data.get("callsign", "").strip().upper()
    if not callsign:
        return jsonify({"error": "callsign requerido"}), 422

    departure = data.get("departure", "").strip().upper()
    arrival = data.get("arrival", "").strip().upper()

    if len(departure) != 4 or len(arrival) != 4:
        return jsonify({"error": "ICAO inválido"}), 422

    rules = (data.get("rules") or "VFR").strip().upper()
    aircraft = (data.get("aircraft") or "C172").strip()
    alternate = (data.get("alternate") or "").strip().upper()
    route = (data.get("route") or "").strip()
    cruise_speed = data.get("cruise_speed")
    departure_time_str = (data.get("departure_time") or "").strip()
    eet_minutes = data.get("eet_minutes")
    endurance_minutes = data.get("endurance_minutes")
    remarks = (data.get("remarks") or "").strip()
    flight_date_str = (data.get("flight_date") or "").strip()
    voice_capability = (data.get("voice_capability") or "V").strip()
    equipment = (data.get("equipment") or "S").strip()
    transponder = (data.get("transponder") or "C").strip()
    wake_turbulence = (data.get("wake_turbulence") or "L").strip()

    # Parsear hora y fecha
    from datetime import time, date
    departure_utc = None
    if departure_time_str:
        try:
            h, m = map(int, departure_time_str.split(":"))
            departure_utc = time(h, m)
        except ValueError:
            pass
    flight_date = None
    if flight_date_str:
        try:
            flight_date = date.fromisoformat(flight_date_str)
        except ValueError:
            pass

    flight_plan = FlightPlanInfo(
        rules=rules,
        departure_icao=departure,
        arrival_icao=arrival,
        alternate_icao=alternate if alternate else None,
        route=route if route else None,
        aircraft_icao_type=aircraft,
        network="VATSIM",
        atc_controlled=False,
    )
    pilot = PilotInfo(
        callsign=callsign,
        license_id=callsign,
    )
    extras = PrefileExtras(
        cruise_speed=cruise_speed,
        departure_utc=departure_utc,
        eet_minutes=eet_minutes,
        endurance_minutes=endurance_minutes,
        remarks=remarks if remarks else None,
        flight_date=flight_date,
        voice_capability=voice_capability,
        equipment=equipment,
        transponder=transponder,
        wake_turbulence=wake_turbulence,
    )

    url = vatsim_prefile_url(flight_plan, pilot, extras)

    return jsonify({"url": url})


@app.route("/api/plan/apply-payload", methods=["POST"])
def apply_payload():
    """apply-payload no está conectado al simulador: no fingir éxito."""
    data = request.get_json() or {}

    passengers = data.get("passengers", 0)
    cargo_kg = data.get("cargo_kg", 0)
    fuel_pct = data.get("fuel_pct", 100)

    # Validación
    if passengers < 0:
        return jsonify({"error": "pasajeros no puede ser negativo"}), 422
    if cargo_kg < 0:
        return jsonify({"error": "carga no puede ser negativa"}), 422
    if fuel_pct < 0 or fuel_pct > 100:
        return jsonify({"error": "combustible debe estar entre 0 y 100"}), 422

    # Sin IPC cliente->web aún: respuesta honesta, no éxito simulado.
    return jsonify({
        "error": "La carga al simulador aún no está disponible: "
                 "no hay conexión con el simulador. No se aplicó nada."
    }), 503


@app.route("/api/registro/upload", methods=["POST"])
@login_requerido
def upload_telemetry():
    """Subir archivo de telemetría (CSV o AVLOG), a la cartilla de quien sube."""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected"}), 400

    ip_cliente = request.remote_addr or "desconocida"
    ok, mensaje, codigo = _importar_vuelo(
        file.read(), file.filename, session.get("user_id", ""), ip_cliente
    )
    return jsonify({"success": ok, "message": mensaje}), codigo


def _importar_vuelo(
    contenido: bytes, nombre_original: str, piloto: str, ip_cliente: str = "desconocida"
) -> tuple[bool, str, int]:
    """El núcleo de una subida: valida, guarda, anota y resume.

    Compartido entre la subida normal (`/api/registro/upload`, el propio
    piloto) y la de gestión (un administrador, en nombre de otro). `piloto`
    es de quién será el vuelo en la cartilla — la comprobación de
    `importacion.revisar` sigue exigiendo que, si el fichero declara un
    dueño, sea justo ese: un admin no puede atribuirle a alguien el vuelo de
    otro, solo completar la cartilla de quien corresponda de verdad.

    🔐 FASE 1: `ip_cliente` se registra en trusted_log.json para auditoría.
    """
    try:
        filename, huella = importacion.revisar(
            contenido, nombre_original, piloto, aeropuertos=AIRPORTS
        )
    except importacion.ImportacionRechazada as rechazo:
        # Registrar rechazos en auditoría
        importacion.auditar_importacion(
            "desconocida", piloto, nombre_original, ip_cliente, f"rechazado: {rechazo.mensaje}"
        )
        return False, rechazo.mensaje, rechazo.codigo

    target_dir = Path.home() / "EvA" / "grabaciones"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / filename
        # Dos vuelos distintos pueden traer el mismo nombre: se busca uno
        # libre en vez de pisar lo que ya está en la cartilla.
        filepath = _ruta_libre(filepath)
        filepath.write_bytes(contenido)
    except OSError as e:
        # Registrar fallos de guardado
        importacion.auditar_importacion(huella, piloto, filename, ip_cliente, f"error al guardar: {e}")
        return False, f"Error al guardar: {e}", 500

    # Solo se anota cuando el fichero está escrito: si falla el guardado, el
    # vuelo tiene que poder volver a intentarse.
    importacion.anotar(huella, piloto, filepath.name)

    # 🔐 FASE 1: Registrar en log de auditoría
    importacion.auditar_importacion(huella, piloto, filepath.name, ip_cliente)

    _resumir_para_estadisticas(huella, filepath, piloto)
    return True, f"Vuelo importado: {filepath.name}", 200


def info_aeropuerto(icao: str) -> dict:
    """Resuelve aeropuerto: aerodromos_es primero (más rico), airports.json como fallback.

    OC-05 §2.4: `airports.json` global sigue siendo el fallback para los
    aeropuertos no españoles.
    """
    icao = icao.upper()

    # 1. Intentar aerodromos_es
    try:
        with cuentas.conexion() as con:
            row = con.execute(
                "SELECT * FROM aerodromos_es WHERE icao = ?", (icao,)
            ).fetchone()
        if row:
            return dict(row)
    except Exception:  # noqa: BLE001 — si la tabla no existe aún, fallback
        pass

    # 2. Fallback a airports.json global
    return AIRPORTS.get(icao, {})


RUTA_VUELTA_ESPANA = "vae-2026"


@app.route("/vuelta-espana")
@login_requerido
def vuelta_espana():
    """Las 21 etapas de la Vuelta a España y qué lleva hecho el piloto.

    Sin orden obligatorio: cada etapa se completa en el momento en que se
    sube un vuelo con ese origen y destino, la que sea. No hace falta haber
    volado la anterior.
    """
    piloto = piloto_actual()
    etapas = []
    try:
        with cuentas.conexion() as con:
            filas = con.execute(
                """SELECT r.*, p.estado, p.completada_en, p.vuelo_huella
                   FROM rutas_vfr r
                   LEFT JOIN progreso_rutas p
                     ON p.ruta_id = r.id AND p.license_id = ?
                   WHERE r.route_id = ? AND r.is_active = 1
                   ORDER BY r.stage_number""",
                (piloto, RUTA_VUELTA_ESPANA),
            ).fetchall()
            etapas = [dict(f) for f in filas]
    except Exception:  # noqa: BLE001 — sin datos importados, la página no revienta
        etapas = []

    completadas = [e for e in etapas if e.get("estado") == "completada"]
    distancia_total = sum(e["distance_nm"] or 0 for e in etapas)
    distancia_hecha = sum(e["distance_nm"] or 0 for e in completadas)

    return render_template(
        "vuelta_espana.html",
        etapas=etapas,
        total_etapas=len(etapas),
        completadas=len(completadas),
        distancia_total=distancia_total,
        distancia_hecha=distancia_hecha,
    )


def _etapa_de_vuelta_espana(origen: str, destino: str) -> Optional[dict]:
    """¿Este origen/destino es una etapa activa de la Vuelta a España?

    Devuelve la fila de `rutas_vfr` (como dict) o `None`. Se usa tanto para
    avisar en la ficha de un vuelo como para la propia página de la Vuelta.
    """
    try:
        with cuentas.conexion() as con:
            fila = con.execute(
                """SELECT * FROM rutas_vfr
                   WHERE route_id = ? AND origin_icao = ? AND destination_icao = ?
                   AND is_active = 1""",
                (RUTA_VUELTA_ESPANA, origen.upper(), destino.upper()),
            ).fetchone()
            return dict(fila) if fila else None
    except Exception:  # noqa: BLE001 — una tabla que falte no debe romper la ficha
        return None


def _verificar_progreso_rutas(huella: str, flight, piloto: str) -> None:
    """Detecta si un vuelo completó una etapa de la Vuelta a España VFR.

    OC-05 §3.5. Añade `progreso_rutas` con estado `completada` sin duplicar la
    etapa si un piloto ya la completó antes. Nunca debe tirar la subida.
    """
    origen = flight.flight_plan.departure_icao.upper()
    destino = flight.flight_plan.arrival_icao.upper()

    try:
        with cuentas.conexion() as con:
            rutas = con.execute(
                """SELECT id FROM rutas_vfr
                   WHERE origin_icao = ? AND destination_icao = ? AND is_active = 1""",
                (origen, destino),
            ).fetchall()

            for ruta in rutas:
                ya = con.execute(
                    """SELECT 1 FROM progreso_rutas
                       WHERE license_id = ? AND ruta_id = ? AND estado = 'completada'""",
                    (piloto, ruta["id"]),
                ).fetchone()

                if not ya:
                    con.execute(
                        """INSERT OR REPLACE INTO progreso_rutas
                           (license_id, ruta_id, estado, vuelo_huella, completada_en)
                           VALUES (?, ?, 'completada', ?, ?)""",
                        (piloto, ruta["id"], huella, cuentas._ahora()),
                    )
    except Exception:  # noqa: BLE001 — nunca romper la subida del piloto
        pass


def _resumir_para_estadisticas(huella: str, filepath: Path, piloto: str) -> None:
    """Añade el vuelo al Home de la aerolínea. Nunca rompe la subida.

    Es un resumen agregado, no la cartilla del piloto: si algo falla aquí
    (un log raro, telemetría corta), el vuelo ya está a salvo en la cartilla
    y no hace falta que el piloto se entere de este paso interno.
    """
    try:
        if filepath.name.endswith(".avlog.json"):
            flight = load_flight(filepath)
            if flight is None:
                return
            perfil = get_profile(DEFAULT_PROFILE, PROFILES)
            aeronave = AIRCRAFT.get(flight.flight_plan.aircraft_icao_type)
            verdict = evaluate_flight(flight, perfil, aircraft=aeronave)
            fecha = (
                flight.timing.block_off_utc.isoformat()
                if flight.timing and flight.timing.block_off_utc
                else None
            )
            # Llegado hasta aquí el vuelo ya es completo (lo filtró
            # `importacion.revisar` antes de escribirlo): queda siempre en
            # la cartilla. Pero solo el aprobado cuenta para estadísticas —
            # el suspenso se queda en la cartilla como "completo suspenso".
            if verdict.passed:
                estadisticas.registrar_avlog(
                    huella, flight, verdict, perfil=DEFAULT_PROFILE, fecha=fecha
                )
            # NUEVO (OC-05): verificar progreso en Vuelta a España
            _verificar_progreso_rutas(huella, flight, piloto)
        elif filepath.name.endswith(".csv"):
            _puntos, resumen = FStelemetryCSVReader.read_csv(filepath)
            if resumen:
                estadisticas.registrar_csv(
                    huella,
                    piloto,
                    distancia_nm=resumen.distance_nm,
                    duracion_min=resumen.flight_time_min,
                )
    except Exception as exc:  # noqa: BLE001 — nunca debe tirar la subida
        app.logger.warning("No se pudo resumir %s para estadísticas: %s", filepath.name, exc)


def _ruta_libre(path: Path) -> Path:
    """Primer nombre sin usar a partir del propuesto."""
    if not path.exists():
        return path
    # `.avlog.json` son dos sufijos: se parte por el primer punto para no
    # acabar con nombres como `vuelo.avlog_2.json`.
    raiz, punto, sufijos = path.name.partition(".")
    contador = 2
    while True:
        candidato = path.with_name(f"{raiz}_{contador}{punto}{sufijos}")
        if not candidato.exists():
            return candidato
        contador += 1


if __name__ == "__main__":
    # El puerto por defecto sigue siendo el 5000; PORT permite levantar una
    # segunda instancia al lado sin tocar la que ya esté corriendo.
    puerto = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, host="127.0.0.1", port=puerto, use_reloader=False)
