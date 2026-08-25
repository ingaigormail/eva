"""EvA - interfaz de grabacion de vuelos.

Ventana pequena, pensada para dejarla en una esquina de la pantalla mientras
se vuela. Todo lo demas (conexion al simulador, muestreo, deteccion de
eventos, escritura del log) ocurre por debajo sin que el piloto tenga que ver
una consola.

Nada que el simulador pueda decirnos se le pregunta al piloto. El indicativo,
la matricula, el tipo de avion y la ruta salen del propio simulador y del
plan de vuelo cargado; van al fichero, pero no ocupan sitio en la ventana.
Lo que si se muestra es lo que el piloto necesita vigilar mientras vuela:
el tiempo grabado, el transpondedor y en que estado esta EvA.

Dos formas de grabar:

- **Automatico**: la maquina de estados vigila el vuelo y graba sola desde la
  carrera de despegue hasta que el avion se detiene tras aterrizar.
- **Manual**: el piloto decide con el boton.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox
from typing import Optional

from . import __version__
from . import debuglog, paths, plan_web, settings as settings_module, timing
from .connectors.base import TRANSPONDER_LABELS, SimState
from .connectors.flight_plan import read_flight_plan
from .connectors.sim_poller import SimPoller
from .connectors.simconnect_client import SimConnectConnector
from .recorder import flight_log_writer as writer
from .recorder.flight_log_writer import FlightRecorder
from .recorder.flight_state_machine import FlightState, FlightStateMachine
from .schema import FlightPlanInfo, PilotInfo
from .settings import MODO_AUTOMATICO, MODO_MANUAL
from .simdetect import is_msfs_running
from .vpilot import is_vpilot_running

APP_NAME = "EvA Grabador"

#: La cartilla del piloto: la lista de sus vuelos registrados, que es también
#: donde se importa el `.avlog.json` recién grabado. Se entra con el usuario
#: con el que se dio de alta.
#:
#: EvA no sube el fichero por su cuenta: cada piloto puede tener las
#: grabaciones en otra carpeta, así que decide él qué importar y cuándo.
#:
#: La dirección sale de las preferencias (`settings.eva_url`), que apuntan al
#: servidor de verdad. Estuvo fija en `http://127.0.0.1:5000` y era un enlace
#: muerto para cualquiera que no tuviera el servidor de desarrollo levantado
#: en su propio equipo — es decir, para todos los pilotos.
RUTA_CARTILLA = "/registro"

# Colores claros (coherencia con web D2/D6/D7)
BG = "#eef1f6"
PANEL = "#ffffff"
FG = "#1e293b"
FG_DIM = "#7c8698"
ACCENT = "#2563eb"
RED = "#dc2626"
GREEN = "#16a34a"
GREY = "#9ca3af"
BORDER = "#cbd5e1"


def _apply_icon(root: tk.Tk) -> None:
    """Intenta aplicar el icono de EvA a la ventana."""
    try:
        ico = paths.assets_dir() / "eva.ico"
        if ico.exists():
            root.iconbitmap(str(ico))
    except Exception:
        pass


def _quitar_controles_nativos(root: tk.Tk) -> None:
    """Quita el minimizar y el cerrar (✕) de la barra de título de Windows.

    Ya hay un botón "minimizar" propio en la interfaz (ver `_minimize`, que
    no reduce a la barra de tareas sino que deja un widget flotante sobre el
    simulador), así que el minimizar nativo es redundante y confunde: el
    piloto puede pulsar el equivocado y esperar el otro comportamiento.
    Quitar `WS_SYSMENU` se lleva también el aspa nativa y el icono de la
    barra de título; Alt+F4 sigue cerrando la ventana igualmente (no depende
    del menú de sistema), así que no hace falta un botón de cerrar propio.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        GWL_STYLE = -16
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_SYSMENU = 0x00080000
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x2, 0x1, 0x4, 0x20

        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id())
        estilo = user32.GetWindowLongW(hwnd, GWL_STYLE)
        estilo &= ~WS_MINIMIZEBOX
        estilo &= ~WS_MAXIMIZEBOX
        estilo &= ~WS_SYSMENU
        user32.SetWindowLongW(hwnd, GWL_STYLE, estilo)
        user32.SetWindowPos(
            hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def _formato_duracion(minutos: Optional[float]) -> str:
    """Minutos sueltos a algo legible en cabina."""
    if minutos is None:
        return "—"
    total = int(round(minutos))
    horas, resto = divmod(total, 60)
    return f"{horas} h {resto:02d} min" if horas else f"{resto} min"


def _formato_distancia(millas: Optional[float]) -> str:
    if millas is None:
        return "—"
    return f"{millas:,.1f} NM".replace(",", ".")


def _formato_combustible(kilos: Optional[float]) -> str:
    if kilos is None:
        return "—"
    return f"{kilos:,.0f} kg".replace(",", ".")


def _describir_ruta(resumen: dict) -> str:
    """Origen y destino del vuelo, o un aviso si no se declararon.

    Los aeródromos salen del plan que el piloto haya puesto en las
    preferencias. Si no puso ninguno, se dice: es preferible a inventarlos.
    """
    salida = (resumen.get("salida") or "").strip()
    llegada = (resumen.get("llegada") or "").strip()
    if salida and llegada:
        return f"{salida} → {llegada}"
    if salida or llegada:
        return f"{salida or '????'} → {llegada or '????'}"
    return "Sin plan de vuelo declarado"


def _open_folder(path: Path) -> None:
    """Abre la carpeta en el explorador."""
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


class EvaApp:
    """Ventana de grabacion de vuelos."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        # La versión, en el título y abajo del todo. Cuando un piloto
        # reporta un fallo, lo primero que hace falta saber es con cuál
        # estaba volando — y no siempre se acuerda de cuándo actualizó.
        self.root.title(f"{APP_NAME}  v{__version__}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        _apply_icon(self.root)
        self.root.update_idletasks()
        _quitar_controles_nativos(self.root)

        # Ventana siempre al frente
        self.root.attributes("-topmost", True)

        self.settings = settings_module.load(paths.settings_file())

        # Salida/llegada mostradas en cabecera: lo que el piloto haya puesto
        # en preferencias, hasta que se detecte el plan cargado en MSFS (más
        # fiable, ver `connectors.flight_plan`).
        self._plan_salida = self.settings.salida
        self._plan_llegada = self.settings.llegada
        self._route_blink_on = False

        # Plan preparado en la web de EvA. Se pide por detrás (ver
        # `_plan_de_la_web`); hasta que llegue la primera respuesta se sigue
        # tirando del `.PLN` o de las preferencias, como siempre.
        self._plan_web: Optional[plan_web.PlanWeb] = None
        self._plan_web_pedido_en = 0.0
        self._plan_web_pidiendo = False

        # Datos que el simulador no ha sabido dar en algún momento. Solo
        # crece: cada uno se apunta una vez (ver `_avisar_datos_que_faltan`).
        self._datos_que_faltaban: set[str] = set()

        # Bitácora de eventos (ver `_apuntar_evento`). La lista existe desde
        # el arranque aunque la ventana no se abra nunca.
        self._eventos: list[str] = []
        self._eventos_window: Optional[tk.Toplevel] = None
        self._eventos_text: Optional[tk.Text] = None
        self._ultimo_motivo = ""
        self._ultimo_estado_mostrado = ""
        self._ultimo_avion = ""

        self.recorder: Optional[FlightRecorder] = None
        self.state_machine: Optional[FlightStateMachine] = None
        self.connector: Optional[SimConnectConnector] = None

        # SimConnect solo se puede consultar desde el hilo que abrió la
        # conexión. El poller es ese hilo: tanto la ventana como el grabador
        # leen lo que él publica, nunca el conector directamente.
        self.poller: Optional[SimPoller] = None

        self._recording = False
        self._minimized = False
        self._led_window: Optional[tk.Toplevel] = None
        self._led_mini: Optional[tk.Label] = None
        self._led_time: Optional[tk.Label] = None
        self._msfs_connected = False

        # Marca de la última vuelta del modo automático, para darle a la
        # máquina de estados el tiempo transcurrido de verdad.
        self._ultimo_tick: Optional[float] = None

        # Último vuelo cerrado, para poder abrir su fichero.
        self.ultimo_vuelo: Optional[Path] = None

        self._build_ui()
        self._connect_sim()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._refresh_flight_plan_display()
        self._parpadear_led_ruta()
        self._poll_status()
        self._update_sim_display()

    def _build_ui(self) -> None:
        """Construye la interfaz."""
        pilot_id = self.settings.license_id or "PILOT"

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(padx=16, pady=16)

        # Cabecera: cuatro avisos con el mismo criterio y el mismo tamaño —
        # verde es "lo tengo", gris o rojo es "me falta". Antes el LED del
        # piloto era en realidad el del simulador (confuso) y era el doble de
        # grande que el de la ruta.
        # Piloto y ruta comparten fila: son las dos señas de "qué vuelo es
        # este", y separadas ocupaban el doble sin decir más.
        #
        # El LED de la ruta avisa si falta: rojo parpadeante hasta que haya
        # salida Y llegada, verde fijo en cuanto las hay (ver
        # `_refresh_flight_plan_display` y `_parpadear_led_ruta`). Grabar
        # está bloqueado mientras esté en rojo.
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 8))

        tk.Label(
            header, text="👤", bg=BG, fg=FG_DIM, font=("Segoe UI Emoji", 11)
        ).pack(side="left", padx=(0, 4))
        self.led_piloto = self._crear_led(header)
        self.led_piloto.pack(side="left", padx=(0, 5))
        tk.Label(
            header,
            text=pilot_id,
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 12)
        ).pack(side="left", padx=(0, 12))

        route_frame = tk.Frame(header, bg=BG)
        route_frame.pack(side="left")

        self.route_led = self._crear_led(route_frame, fg=RED)
        self.route_led.pack(side="left", padx=(0, 5))
        tk.Label(
            route_frame, text="🗺", bg=BG, fg=FG_DIM, font=("Segoe UI Emoji", 10)
        ).pack(side="left", padx=(0, 4))

        self.route_label = tk.Label(
            route_frame,
            text=_describir_ruta({"salida": self._plan_salida, "llegada": self._plan_llegada}),
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 10),
        )
        self.route_label.pack(side="left")

        # Simulador y vPilot, con el mismo criterio que los de arriba: verde
        # es detectado, gris es que no está.
        deteccion_frame = tk.Frame(outer, bg=BG)
        deteccion_frame.pack(fill="x", pady=(0, 8))

        tk.Label(
            deteccion_frame, text="🔌", bg=BG, fg=FG_DIM,
            font=("Segoe UI Emoji", 10),
        ).pack(side="left", padx=(0, 5))

        self.led_msfs = self._crear_led(deteccion_frame)
        self.led_msfs.pack(side="left", padx=(0, 5))
        tk.Label(
            deteccion_frame, text="SIMULADOR", bg=BG, fg=FG_DIM,
            font=("Segoe UI Semibold", 8),
        ).pack(side="left", padx=(0, 14))

        self.led_vpilot = self._crear_led(deteccion_frame)
        self.led_vpilot.pack(side="left", padx=(0, 5))
        tk.Label(
            deteccion_frame, text="VPILOT", bg=BG, fg=FG_DIM,
            font=("Segoe UI Semibold", 8),
        ).pack(side="left")

        # Atajo para enlazar el grabador con la web. Se enseña solo mientras
        # no haya clave: una vez enlazado no pinta nada y estorbaría.
        self.route_link = tk.Label(
            outer,
            text="Traer el plan de la web",
            bg=BG,
            fg=ACCENT,
            font=("Segoe UI", 8, "underline"),
            cursor="hand2",
        )
        self.route_link.bind("<Button-1>", lambda _e: self._enlazar_con_la_web())

        def _al_empaquetar_enlace() -> None:
            self.route_link.pack(fill="x", pady=(0, 6))

        self._empaquetar_enlace_web = _al_empaquetar_enlace
        self._actualizar_enlace_web()

        # El avión que se está volando. Se graba en el fichero y decide qué
        # límites del POH se aplican, así que conviene poder comprobarlo de
        # un vistazo antes de despegar.
        self.avion_label = tk.Label(
            outer, text="Avión: —", bg=BG, fg=FG_DIM,
            font=("Segoe UI Semibold", 9),
        )
        self.avion_label.pack(fill="x", pady=(0, 10))

        # Panel principal
        panel = tk.Frame(outer, bg=PANEL, relief="flat", bd=1)
        panel.pack(fill="both", expand=True, padx=0, pady=0)

        inner = tk.Frame(panel, bg=PANEL, padx=16, pady=16)
        inner.pack(fill="both", expand=True)

        # Estado de grabacion
        self.status_label = tk.Label(
            inner,
            text="DETENIDO",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI Semibold", 16)
        )
        self.status_label.pack()

        self.time_label = tk.Label(
            inner,
            text="00:00:00",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 10)
        )
        self.time_label.pack(pady=(4, 0))

        # Qué está haciendo el modo automático, en una frase.
        self.status_detail = tk.Label(
            inner,
            text="",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 8),
            wraplength=190,
            justify="center",
        )
        self.status_detail.pack(pady=(6, 0))

        # Estado interno de la máquina, en crudo. La frase de arriba es para
        # el piloto; esto es para saber en qué fase está exactamente, que es
        # lo que hacía falta cuando la grabación no arrancaba.
        self.fase_label = tk.Label(
            inner, text="—", bg=PANEL, fg=FG_DIM,
            font=("Consolas", 7),
        )
        self.fase_label.pack(pady=(2, 0))

        self.eventos_link = tk.Label(
            inner, text="Ver eventos", bg=PANEL, fg=ACCENT,
            font=("Segoe UI", 7, "underline"), cursor="hand2",
        )
        self.eventos_link.bind("<Button-1>", lambda _e: self._abrir_ventana_eventos())
        self.eventos_link.pack(pady=(2, 0))

        self.transponder_label = tk.Label(
            inner,
            text="ALT: -----ft | GS: ---kt | ---",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 8)
        )
        self.transponder_label.pack(pady=(8, 0))

        # LUCES SOP: un badge por luz, verde encendida / rojo apagada / gris
        # si el simulador no da ese dato. Mismo patrón visual que el XPDR de
        # al lado: de un vistazo se ve qué falta antes de rodar.
        estado_frame = tk.Frame(inner, bg=PANEL)
        estado_frame.pack(pady=(6, 0))

        self.xpdr_badge = tk.Label(
            estado_frame, text="XPDR ---", bg=GREY, fg="white",
            font=("Segoe UI Semibold", 8), padx=6, pady=2,
        )
        self.xpdr_badge.pack(side="left", padx=(0, 8))

        tk.Label(
            estado_frame, text="LUCES SOP", bg=PANEL, fg=FG_DIM,
            font=("Segoe UI", 7, "bold"),
        ).pack(side="left", padx=(0, 4))

        # Orden y letra tal como se comprueban en el rodaje: Beacon, Nav,
        # Taxi, Landing, Strobe — coincide con las reglas taxi_light/
        # strobe_airborne/beacon_airborne/nav_light_airborne del motor.
        self._luces_badges: dict[str, tk.Label] = {}
        for letra, campo in (
            ("B", "beacon_light"), ("N", "nav_light"), ("T", "taxi_light"),
            ("L", "landing_light"), ("S", "strobe_light"),
        ):
            badge = tk.Label(
                estado_frame, text=letra, bg=GREY, fg="white",
                font=("Segoe UI Semibold", 8), width=2, padx=1, pady=2,
            )
            badge.pack(side="left", padx=1)
            self._luces_badges[campo] = badge

        # Selector de modo: dos botones, no radios. El modo elegido se ve
        # relleno; el otro, sin relleno.
        mode_frame = tk.Frame(inner, bg=PANEL)
        mode_frame.pack(fill="x", pady=(12, 0))

        self.mode_var = tk.StringVar(value=self.settings.modo)

        self.boton_manual = tk.Label(
            mode_frame,
            text="MANUAL",
            font=("Segoe UI Semibold", 9),
            pady=6,
            cursor="hand2",
        )
        self.boton_manual.pack(side="left", fill="x", expand=True)
        self.boton_manual.bind(
            "<Button-1>", lambda _e: self._set_mode(MODO_MANUAL)
        )

        self.boton_automatico = tk.Label(
            mode_frame,
            text="AUTOMATICO",
            font=("Segoe UI Semibold", 9),
            pady=6,
            cursor="hand2",
        )
        self.boton_automatico.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.boton_automatico.bind(
            "<Button-1>", lambda _e: self._set_mode(MODO_AUTOMATICO)
        )

        self._refresh_mode_buttons()

        # Boton para empezar/parar
        self.record_button = tk.Label(
            inner,
            text="GRABAR",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI Semibold", 11),
            pady=8,
            cursor="hand2"
        )
        self.record_button.pack(fill="x", pady=(8, 0))
        self.record_button.bind("<Button-1>", lambda _: self._on_button_click())

        # Solo aparece cuando hay un vuelo recién guardado (ver
        # `_mostrar_boton_finalizar`); por eso se crea sin empaquetar.
        self.boton_finalizar = tk.Label(
            inner,
            text="FINALIZAR VUELO",
            bg=GREEN,
            fg="white",
            font=("Segoe UI Semibold", 11),
            pady=8,
            cursor="hand2",
        )
        self.boton_finalizar.bind("<Button-1>", lambda _e: self._finalizar_vuelo())

        # Boton Minimizar: con pinta de boton (borde, fondo, hover) para que
        # se note que es clicable, ya que sustituye por completo al
        # minimizar nativo de Windows (ver `_quitar_controles_nativos`).
        links = tk.Frame(outer, bg=BG)
        links.pack(fill="x", pady=(8, 0))

        self._minimize_button = tk.Label(
            links,
            text="▁  Minimizar",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI Semibold", 8),
            relief="solid",
            borderwidth=1,
            highlightbackground=BORDER,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        self._minimize_button.pack(side="left")
        self._minimize_button.bind("<Button-1>", lambda _e: self._minimize())
        self._minimize_button.bind(
            "<Enter>", lambda _e: self._minimize_button.configure(bg=ACCENT, fg="white")
        )
        self._minimize_button.bind(
            "<Leave>", lambda _e: self._minimize_button.configure(bg=PANEL, fg=FG_DIM)
        )

        # Cerrar. Hacía falta uno propio: `_quitar_controles_nativos` se
        # lleva el aspa de la barra de título, así que sin esto la única
        # forma de salir era Alt+F4, que no es evidente.
        self._close_button = tk.Label(
            links,
            text="✕  Cerrar",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI Semibold", 8),
            relief="solid",
            borderwidth=1,
            highlightbackground=BORDER,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        self._close_button.pack(side="left", padx=(8, 0))
        self._close_button.bind("<Button-1>", lambda _e: self._cerrar())
        self._close_button.bind(
            "<Enter>", lambda _e: self._close_button.configure(bg=RED, fg="white")
        )
        self._close_button.bind(
            "<Leave>", lambda _e: self._close_button.configure(bg=PANEL, fg=FG_DIM)
        )

        tk.Label(
            links, text=f"v{__version__}", bg=BG, fg=FG_DIM,
            font=("Segoe UI", 8),
        ).pack(side="right")

        self._set_status()

    def _cerrar(self) -> None:
        """Cierra EvA, avisando si hay un vuelo a medio grabar.

        Salir con la grabación en marcha pierde el vuelo, así que se
        pregunta. El fichero parcial queda en disco de todas formas (ver
        `flight_log_writer`), pero el piloto tiene que saberlo antes.
        """
        if self._recording:
            seguir = messagebox.askyesno(
                APP_NAME,
                "Estás grabando un vuelo.\n\n"
                "Si cierras ahora, el vuelo no se cerrará como es debido.\n"
                "¿Seguro que quieres salir?",
                icon="warning",
                default="no",
            )
            if not seguir:
                return
            self._apuntar_evento("EvA cerrado con una grabación en marcha")

        self.root.destroy()

    def _set_mode(self, modo: str) -> None:
        """Cambia el modo de grabacion y lo recuerda para la proxima vez."""
        if modo == self.mode_var.get():
            return
        self.mode_var.set(modo)
        self.settings.modo = modo
        settings_module.save(self.settings, paths.settings_file())

        # La máquina arranca de cero al volver a automático: lo que pasara
        # mientras se grababa a mano no cuenta para decidir el despegue.
        if self.state_machine is not None:
            self.state_machine.reset()
        self._ultimo_tick = None
        self.status_detail.configure(text="")

        self._refresh_mode_buttons()
        self._set_button_idle()

    def _refresh_mode_buttons(self) -> None:
        """Resalta el modo activo de los dos botones."""
        activo = self.mode_var.get()
        for boton, modo in (
            (self.boton_manual, MODO_MANUAL),
            (self.boton_automatico, MODO_AUTOMATICO),
        ):
            if modo == activo:
                boton.configure(bg=ACCENT, fg="white")
            else:
                boton.configure(bg=PANEL, fg=FG_DIM)

    def _set_status(self) -> None:
        """Actualiza el estado visual."""
        if self._recording:
            self.status_label.configure(text="GRABANDO", fg=RED)
        else:
            self.status_label.configure(text="DETENIDO", fg=FG_DIM)

    def _set_button_idle(self) -> None:
        """Actualiza el boton segun el estado.

        En automático el botón no manda: informa. Quien decide es la máquina
        de estados, y el piloto no tiene que pulsar nada.
        """
        automatico = self.mode_var.get() == MODO_AUTOMATICO

        if not self._msfs_connected:
            self.record_button.configure(
                text="MSFS CERRADO", bg=GREY, cursor="arrow"
            )
        elif self._recording:
            self.record_button.configure(
                text="GRABANDO" if automatico else "PARAR",
                bg=RED,
                cursor="arrow" if automatico else "hand2",
            )
        elif automatico:
            self.record_button.configure(
                text="EN AUTOMÁTICO", bg="#f59e0b", cursor="arrow"
            )
        else:
            self.record_button.configure(text="GRABAR", bg=ACCENT, cursor="hand2")

        self._refresh_mini()

    def _on_button_click(self) -> None:
        """Maneja clic en boton de grabacion."""
        # Con un vuelo recién aterrizado sin finalizar, el clic lo finaliza:
        # empezar otra grabación encima sería tirar el vuelo por error.
        if not self._recording and self.ultimo_vuelo is not None:
            self._finalizar_vuelo()
            return

        if self.mode_var.get() == MODO_AUTOMATICO:
            # En automático empieza y para sola: pulsar no debe adelantarse a
            # la máquina de estados ni cortarle un vuelo a medias.
            return

        if not self._msfs_connected:
            messagebox.showerror(
                APP_NAME,
                "MSFS no está abierto.\n\n"
                "Arranca el simulador y carga un vuelo; el indicador de arriba "
                "se pondrá en verde cuando EvA lo detecte."
            )
            return

        if not self._recording and not self._ruta_completa():
            messagebox.showerror(
                APP_NAME,
                "Falta origen o destino del plan de vuelo.\n\n"
                "Carga un plan en MSFS o ponlos en preferencias antes de "
                "grabar; el indicador de arriba se pone en verde en cuanto "
                "estén los dos."
            )
            return

        if self._recording:
            self._stop()
        else:
            self._start()

    def _build_flight_plan(self) -> FlightPlanInfo:
        """Datos del plan que acompañan al vuelo grabado.

        Solo se rellena lo que se sabe de verdad. Los aeródromos salen de las
        preferencias y se dejan vacíos si el piloto no los ha puesto: inventar
        un ICAO metería un dato falso en el log, que es peor que no tenerlo.
        """
        # El avión, del simulador. Esto era un `getattr` sobre un atributo
        # que `SimState` no tenía, así que devolvía None siempre y el avión
        # no se grababa nunca — y sin él, las reglas que dependen del POH
        # (`structural_overspeed`) no podían aplicarse jamás.
        estado = self.poller.latest if self.poller is not None else None
        aircraft_type = estado.aircraft_type if estado else None
        matricula = estado.aircraft_registration if estado else None

        return FlightPlanInfo(
            rules="VFR",
            departure_icao=self._plan_salida,
            arrival_icao=self._plan_llegada,
            alternate_icao=None,
            route=None,
            aircraft_icao_type=aircraft_type,
            aircraft_registration=matricula,
            # Que vPilot esté arrancado es lo único que se puede afirmar sin
            # preguntarle a la red. Si no lo está, el vuelo es offline.
            network="VATSIM" if is_vpilot_running() else "OFFLINE",
            # No se sabe aún si habrá ATC: se marca al cerrar el vuelo, si se
            # detecta. Empezar en False es la afirmación prudente.
            atc_controlled=False,
        )

    def _start(self) -> None:
        """Inicia grabacion."""
        if self._recording:
            return

        # Cubre también el modo automático: la máquina de estados llama aquí
        # directo, sin pasar por `_on_button_click`. Sin salida/llegada no
        # se graba; en cuanto el LED se ponga verde, el siguiente intento
        # (automático reintenta solo, manual con otro clic) sí arranca.
        if not self._ruta_completa():
            return

        # Puede estar abierto y aún no responder (cargando, o en el menú):
        # se reintenta aquí antes de rendirse.
        self._try_connect()
        if self.poller is None or not self.poller.connected:
            messagebox.showerror(
                APP_NAME,
                "MSFS está abierto pero todavía no responde.\n\n"
                "Suele pasar mientras carga o en el menú principal: entra en "
                "el vuelo y vuelve a darle a GRABAR."
            )
            return

        try:
            self.recorder = FlightRecorder(
                # El grabador consume lo que publica el poller, no el conector.
                source=self.poller.reading_after,
                pilot=PilotInfo(
                    license_id=self.settings.license_id,
                    # Si no hay indicativo, el vuelo se identifica por la
                    # licencia del piloto antes que por un relleno.
                    callsign=(
                        self.settings.indicativo
                        or self.settings.license_id
                        or "SIN-DISTINTIVO"
                    ),
                ),
                flight_plan=self._build_flight_plan(),
                output_dir=self.recordings_dir(),
                autosave_interval_s=self.settings.intervalo_autoguardado_s,
                # El grabador trabaja en su propio hilo: sin esto, un fallo
                # suyo a mitad de vuelo no llegaría a ninguna parte.
                on_error=lambda exc: debuglog.fallo("hilo del grabador", exc),
            )
            self.recorder.start()
            debuglog.apunte(
                f"grabacion iniciada en {self.recordings_dir()} "
                f"(modo {self.mode_var.get()})"
            )
        except Exception as exc:
            self.recorder = None
            messagebox.showerror(
                APP_NAME,
                f"No se pudo empezar a grabar:\n\n{exc}\n\n"
                "Comprueba que tienes permiso de escritura en la carpeta de "
                "grabaciones."
            )
            return

        self._recording = True
        self._set_button_idle()
        self._set_status()
        self._refresh_mini()

    def _stop(self) -> None:
        """Detiene la grabacion y escribe el fichero del vuelo."""
        if not self._recording:
            return

        self._recording = False
        destino: Optional[Path] = None
        error: Optional[Exception] = None

        if self.recorder is not None:
            try:
                destino = self.recorder.stop()
            except Exception as exc:  # el vuelo ya está grabado en el parcial
                error = exc
            self.recorder = None

        self._set_button_idle()
        self._set_status()
        self._refresh_mini()

        if error is not None:
            messagebox.showerror(
                APP_NAME,
                f"La grabación se detuvo pero no se pudo cerrar el fichero:\n\n"
                f"{error}\n\nEl vuelo sigue en el fichero parcial de la carpeta "
                "de grabaciones."
            )
        elif destino is not None:
            self.ultimo_vuelo = destino
            debuglog.apunte(f"vuelo guardado en {destino}")
            # No se abre el resumen solo: en automático el vuelo puede acabar
            # con el piloto aún en cabina. Se avisa y él decide cuándo.
            self._mostrar_boton_finalizar()

    # -- fin de vuelo --------------------------------------------------

    def _mostrar_boton_finalizar(self) -> None:
        """Saca el botón de finalizar cuando hay un vuelo recién guardado."""
        self.boton_finalizar.pack(fill="x", pady=(6, 0))
        self._refresh_mini()

    def _ocultar_boton_finalizar(self) -> None:
        self.ultimo_vuelo = None
        self.boton_finalizar.pack_forget()
        self._refresh_mini()

    def _finalizar_vuelo(self) -> None:
        """Enseña qué se ha grabado y encadena con la pantalla de importar."""
        if self.ultimo_vuelo is None:
            return

        if self._minimized:
            self._restore()

        resumen = writer.describe_flight(self.ultimo_vuelo)
        if resumen is None:
            messagebox.showwarning(
                APP_NAME,
                f"El vuelo se guardó en:\n\n{self.ultimo_vuelo}\n\n"
                "pero el fichero no se ha podido volver a leer para resumirlo.",
            )
            self._ocultar_boton_finalizar()
            self._abrir_cartilla()
            return

        self._ventana_resumen(resumen)

    def _ventana_resumen(self, resumen: dict) -> None:
        """Pantalla de fin de vuelo: qué se grabó y dónde quedó."""
        ventana = tk.Toplevel(self.root)
        ventana.title("Vuelo finalizado")
        ventana.configure(bg=BG)
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        ventana.transient(self.root)

        marco = tk.Frame(ventana, bg=BG, padx=18, pady=16)
        marco.pack(fill="both", expand=True)

        tk.Label(
            marco,
            text="VUELO GRABADO",
            bg=BG,
            fg=GREEN,
            font=("Segoe UI Semibold", 13),
        ).pack(anchor="w")

        ruta_texto = _describir_ruta(resumen)
        tk.Label(
            marco, text=ruta_texto, bg=BG, fg=FG,
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w", pady=(2, 12))

        tarjeta = tk.Frame(marco, bg=PANEL, padx=14, pady=12)
        tarjeta.pack(fill="x")

        for etiqueta, valor in (
            ("Duración", _formato_duracion(resumen.get("minutos"))),
            ("Distancia", _formato_distancia(resumen.get("distancia_nm"))),
            ("Combustible", _formato_combustible(resumen.get("combustible_kg"))),
            ("Puntos de traza", f"{resumen.get('puntos', 0):,}".replace(",", ".")),
            ("Eventos", str(resumen.get("eventos", 0))),
        ):
            fila = tk.Frame(tarjeta, bg=PANEL)
            fila.pack(fill="x", pady=1)
            tk.Label(
                fila, text=etiqueta, bg=PANEL, fg=FG_DIM,
                font=("Segoe UI", 9), width=16, anchor="w",
            ).pack(side="left")
            tk.Label(
                fila, text=valor, bg=PANEL, fg=FG,
                font=("Segoe UI Semibold", 9), anchor="w",
            ).pack(side="left")

        # El fichero: nombre destacado y carpeta debajo, que es lo que hace
        # falta para encontrarlo al importarlo.
        ruta: Path = resumen["ruta"]
        tk.Label(
            marco, text="FICHERO", bg=BG, fg=FG_DIM,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(12, 0))
        tk.Label(
            marco, text=ruta.name, bg=BG, fg=FG,
            font=("Consolas", 9),
        ).pack(anchor="w")

        carpeta = tk.Label(
            marco, text=str(ruta.parent), bg=BG, fg=ACCENT,
            font=("Segoe UI", 8, "underline"), cursor="hand2",
            wraplength=340, justify="left",
        )
        carpeta.pack(anchor="w")
        carpeta.bind("<Button-1>", lambda _e: _open_folder(ruta.parent))

        boton = tk.Label(
            marco,
            text="ABRIR MI CARTILLA",
            bg=ACCENT, fg="white",
            font=("Segoe UI Semibold", 10),
            pady=9, cursor="hand2",
        )
        boton.pack(fill="x", pady=(14, 0))

        def cerrar_y_importar(*_args) -> None:
            ventana.destroy()
            self._ocultar_boton_finalizar()
            self._abrir_cartilla()

        boton.bind("<Button-1>", cerrar_y_importar)
        # Cerrar por la X hace lo mismo: el vuelo ya está grabado y el
        # siguiente paso siempre es importarlo.
        ventana.protocol("WM_DELETE_WINDOW", cerrar_y_importar)

    def _url_cartilla(self) -> str:
        """La cartilla en el servidor que tenga configurado el piloto."""
        base = (self.settings.eva_url or "").strip().rstrip("/")
        return f"{base}{RUTA_CARTILLA}"

    def _abrir_cartilla(self) -> None:
        """Abre la cartilla del piloto en el navegador."""
        url = self._url_cartilla()
        try:
            webbrowser.open(url, new=0)
            self._apuntar_evento(f"abierta la cartilla: {url}")
        except Exception as exc:
            debuglog.fallo("apertura de la cartilla", exc)
            messagebox.showwarning(
                APP_NAME,
                "No se pudo abrir el navegador con tu cartilla.\n\n"
                f"Ábrela a mano en: {url}",
            )

    def _minimize(self) -> None:
        """Deja solo el botón de grabar con su reloj, sobre el simulador.

        Es una ventana hija, no una segunda `Tk()`: dos raíces son dos
        intérpretes de Tcl, y la ventana principal dejaría de refrescarse.

        Sin barra de título, para que ocupe lo mínimo encima del simulador; se
        arrastra con el ratón desde cualquier punto.
        """
        if self._minimized:
            return

        self._minimized = True
        self.root.withdraw()

        self._led_window = tk.Toplevel(self.root)
        self._led_window.overrideredirect(True)
        self._led_window.configure(bg=FG)
        self._led_window.attributes("-topmost", True)
        self._led_window.geometry(f"+{self.root.winfo_x()}+{self.root.winfo_y()}")

        marco = tk.Frame(self._led_window, bg=FG, padx=10, pady=6)
        marco.pack()

        # El botón: dice en qué estado está y al pulsarlo cambia de estado.
        self._led_mini = tk.Label(
            marco,
            bg=FG,
            font=("Segoe UI Semibold", 10),
            cursor="hand2",
        )
        self._led_mini.pack(side="left")
        self._led_mini.bind("<Button-1>", lambda _e: self._on_button_click())

        self._led_time = tk.Label(
            marco,
            text=self._tiempo_grabado(),
            bg=FG,
            fg="white",
            font=("Consolas", 10),
        )
        self._led_time.pack(side="left", padx=(10, 0))

        # Volver a la ventana entera.
        volver = tk.Label(
            marco,
            text="▣",
            bg=FG,
            fg=FG_DIM,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        volver.pack(side="left", padx=(10, 0))
        volver.bind("<Button-1>", lambda _e: self._restore())

        self._hacer_arrastrable(self._led_window, marco, self._led_time)
        self._refresh_mini()

    def _hacer_arrastrable(self, ventana: tk.Toplevel, *zonas: tk.Widget) -> None:
        """Permite mover una ventana sin barra de título arrastrándola."""
        origen: dict[str, int] = {}

        def pulsar(evento: "tk.Event") -> None:
            origen["x"] = evento.x_root - ventana.winfo_x()
            origen["y"] = evento.y_root - ventana.winfo_y()

        def arrastrar(evento: "tk.Event") -> None:
            if not origen:
                return
            ventana.geometry(
                f"+{evento.x_root - origen['x']}+{evento.y_root - origen['y']}"
            )

        for zona in zonas:
            zona.bind("<Button-1>", pulsar, add="+")
            zona.bind("<B1-Motion>", arrastrar, add="+")

    def _refresh_mini(self) -> None:
        """Pone el botón pequeño acorde al estado real de la grabación."""
        if self._led_mini is None:
            return
        if self._recording:
            self._led_mini.configure(text="● GRABANDO", fg="#fca5a5")
        elif self.ultimo_vuelo is not None:
            # Recién aterrizado: lo siguiente es finalizar, no volver a grabar.
            self._led_mini.configure(text="● VUELO LISTO", fg="#86efac")
        elif not self._msfs_connected:
            self._led_mini.configure(text="● MSFS CERRADO", fg=GREY)
        else:
            self._led_mini.configure(text="● PARADO", fg=GREY)

    def _restore(self) -> None:
        """Restaura ventana principal."""
        if not self._minimized:
            return

        self._minimized = False

        if self._led_window is not None:
            self._led_window.destroy()
            self._led_window = None
            self._led_mini = None
            self._led_time = None

        self.root.deiconify()
        self._set_button_idle()
        self._set_status()

    def _connect_sim(self) -> None:
        """Engancha con el simulador si está abierto.

        Ojo: construir el conector no conecta nada; hay que llamar a
        `connect()`. Sin eso `connected` es siempre False y la ventana
        anuncia "MSFS CERRADO" con el simulador delante.
        """
        self.state_machine = FlightStateMachine()
        self.state_machine.confirmation_liftoff_s = self.settings.segundos_confirmacion_despegue
        self.state_machine.confirmation_landing_s = self.settings.segundos_confirmacion_aterrizaje
        self.state_machine.confirmation_stopped_s = self.settings.segundos_confirmacion_parada

        self._try_connect()

    def _try_connect(self) -> None:
        """Intenta enganchar con el simulador. Silencioso si no se puede.

        Al conectar se arranca el poller, que es quien queda dueño del hilo
        de SimConnect. Nadie más vuelve a tocar el conector.
        """
        if self.poller is not None and self.poller.connected:
            return
        if not is_msfs_running():
            self._drop_connection()
            return
        try:
            conector = SimConnectConnector()
            conector.connect()
        except Exception as exc:
            debuglog.fallo("conexion con SimConnect", exc)
            self._drop_connection()
            return

        self.connector = conector
        self.poller = SimPoller(conector)
        self.poller.start()

    def _drop_connection(self) -> None:
        """Suelta el simulador. No detiene la grabación en curso."""
        if self.poller is not None:
            try:
                self.poller.stop()
            except Exception as exc:
                debuglog.fallo("cierre del poller", exc)
        self.poller = None
        self.connector = None

    def _poll_status(self) -> None:
        """Refresca el estado del simulador y de la grabacion.

        Son dos preguntas distintas: si el simulador está **abierto** se mira
        por proceso (barato y fiable), y si además se puede **hablar** con él
        lo dice el conector. La primera manda en el indicador.
        """
        self._msfs_connected = is_msfs_running()
        if self._msfs_connected:
            self._try_connect()
        else:
            self._drop_connection()

        if self._minimized:
            self._refresh_mini()
        else:
            self.led_msfs.configure(fg=GREEN if self._msfs_connected else GREY)
            # vPilot es lo que conecta a VATSIM: sin él, el vuelo se graba
            # igual pero no queda constancia en la red.
            self.led_vpilot.configure(fg=GREEN if is_vpilot_running() else GREY)
            self.led_piloto.configure(
                fg=GREEN if self.settings.license_id else GREY
            )
            self._set_button_idle()

        self._refresh_flight_plan_display()

        # Cada 5 s: es un vistazo a la lista de procesos, no hace falta más.
        self.root.after(5000, self._poll_status)

    def _refresh_flight_plan_display(self) -> None:
        """Actualiza el origen/destino de la cabecera.

        Prioridad: el plan cargado en el simulador (fichero `.PLN`, es lo
        que el avión va a volar de verdad), luego el que el piloto haya
        preparado en la web de EvA, y por último lo que tenga escrito en
        preferencias.

        El de la web va por delante de las preferencias porque es lo que el
        piloto acaba de declarar para *este* vuelo; las preferencias suelen
        ser de un vuelo anterior que se quedó ahí.
        """
        try:
            detectado = read_flight_plan()
        except Exception as exc:
            debuglog.fallo("lectura del plan de vuelo activo", exc)
            detectado = None

        del_web = self._plan_de_la_web()

        self._plan_salida = (
            (detectado.departure_icao if detectado else None)
            or (del_web.origen if del_web else "")
            or self.settings.salida
        )
        self._plan_llegada = (
            (detectado.arrival_icao if detectado else None)
            or (del_web.destino if del_web else "")
            or self.settings.llegada
        )
        completa = self._ruta_completa()
        self.route_label.configure(
            text=_describir_ruta({"salida": self._plan_salida, "llegada": self._plan_llegada}),
            fg=FG_DIM if completa else RED,
        )

    #: Cada cuánto se le vuelve a preguntar al servidor por el plan. La
    #: cabecera se refresca cada 5 s, pero el plan de la web cambia cuando
    #: el piloto lo guarda, no cada 5 s: preguntarlo tan seguido sería
    #: castigar al servidor para nada.
    _SEGUNDOS_ENTRE_CONSULTAS_WEB = 60.0

    def _plan_de_la_web(self) -> Optional[plan_web.PlanWeb]:
        """El plan de la web, de la caché; lo refresca por detrás si toca.

        Nunca espera a la red: `_refresh_flight_plan_display` corre cada 5 s
        y una petición ahí dejaría la ventana congelada hasta 4 s cada vez.
        Se devuelve lo último que se supo y la respuesta nueva entra en el
        siguiente refresco.
        """
        if not self.settings.clave_grabador:
            return None

        ahora = time.monotonic()
        toca = ahora - self._plan_web_pedido_en >= self._SEGUNDOS_ENTRE_CONSULTAS_WEB
        if toca and not self._plan_web_pidiendo:
            self._plan_web_pedido_en = ahora
            self._plan_web_pidiendo = True
            threading.Thread(target=self._traer_plan_web, daemon=True).start()
        return self._plan_web

    def _traer_plan_web(self) -> None:
        """Consulta el plan en un hilo aparte. No toca ningún widget.

        Solo deja el resultado en un atributo: Tk no admite que se le pinte
        desde otro hilo, así que la cabecera la actualiza el refresco de
        siempre, que va por el hilo principal.
        """
        try:
            self._plan_web = plan_web.ultimo_plan(
                self.settings.eva_url, self.settings.clave_grabador
            )
        except Exception as exc:  # noqa: BLE001 — no puede tumbar el grabador
            debuglog.fallo("lectura del plan de vuelo de la web", exc)
        finally:
            self._plan_web_pidiendo = False

    #: Tamaño único de todos los avisos de la cabecera. Estaban a 16 y a 10
    #: y no había motivo: los cuatro dicen lo mismo (lo tengo / me falta).
    _TAMANO_LED = 11

    def _crear_led(self, padre: tk.Widget, fg: str = GREY) -> tk.Label:
        return tk.Label(
            padre, text="●", bg=BG, fg=fg, font=("Segoe UI", self._TAMANO_LED)
        )

    def _actualizar_enlace_web(self) -> None:
        """Enseña el atajo de enlazar solo mientras no haya clave."""
        if self.settings.clave_grabador:
            self.route_link.pack_forget()
        else:
            self._empaquetar_enlace_web()

    def _enlazar_con_la_web(self) -> None:
        """Pide las credenciales de EvA y las cambia por la clave.

        La contraseña vive lo que dura esta ventana: se manda al servidor y
        se olvida. Lo único que se guarda en `eva.config.json` es la clave
        que devuelve, que solo sirve para leer el plan y se puede anular
        desde la web.
        """
        ventana = tk.Toplevel(self.root)
        ventana.title("Traer el plan de la web")
        ventana.configure(bg=BG)
        ventana.resizable(False, False)
        ventana.attributes("-topmost", True)
        ventana.transient(self.root)

        marco = tk.Frame(ventana, bg=BG, padx=18, pady=16)
        marco.pack(fill="both", expand=True)

        tk.Label(
            marco, text="ENTRAR EN EvA", bg=BG, fg=FG,
            font=("Segoe UI Semibold", 11),
        ).pack(anchor="w")
        tk.Label(
            marco,
            text="Con tu usuario y contraseña de la web. El grabador\n"
                 "cogerá solo el origen y el destino de tu plan.\n"
                 "Tu contraseña no se guarda en este equipo.",
            bg=BG, fg=FG_DIM, font=("Segoe UI", 8), justify="left",
        ).pack(anchor="w", pady=(2, 12))

        tk.Label(marco, text="ID de piloto", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        campo_id = tk.Entry(marco, width=30, font=("Segoe UI", 10))
        campo_id.insert(0, self.settings.license_id or self.settings.indicativo)
        campo_id.pack(anchor="w", pady=(0, 8))

        tk.Label(marco, text="Contraseña", bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        campo_clave = tk.Entry(marco, width=30, show="•", font=("Segoe UI", 10))
        campo_clave.pack(anchor="w", pady=(0, 6))

        aviso = tk.Label(marco, text="", bg=BG, fg=RED, font=("Segoe UI", 8),
                         wraplength=260, justify="left")
        aviso.pack(anchor="w", pady=(0, 8))

        def _entrar() -> None:
            aviso.configure(text="Conectando…", fg=FG_DIM)
            ventana.update_idletasks()
            clave, error = plan_web.obtener_clave(
                self.settings.eva_url, campo_id.get().strip(), campo_clave.get()
            )
            if error:
                aviso.configure(text=error, fg=RED)
                return

            self.settings.clave_grabador = clave
            self.settings.license_id = campo_id.get().strip()
            if not settings_module.save(self.settings, paths.settings_file()):
                aviso.configure(
                    text="Entraste bien, pero no se pudieron guardar las "
                         "preferencias: habrá que repetirlo al reabrir.",
                    fg=RED,
                )
                return

            debuglog.apunte("grabador enlazado con la web de EvA")
            # Que se note enseguida, sin esperar al minuto de la caché.
            self._plan_web_pedido_en = 0.0
            self._actualizar_enlace_web()
            ventana.destroy()
            self._refresh_flight_plan_display()

        boton = tk.Button(
            marco, text="ENTRAR", command=_entrar, bg=ACCENT, fg="#fff",
            font=("Segoe UI Semibold", 9), relief="flat", padx=16, pady=5,
            cursor="hand2", activebackground=ACCENT, activeforeground="#fff",
        )
        boton.pack(anchor="w")

        campo_clave.bind("<Return>", lambda _e: _entrar())
        (campo_clave if campo_id.get() else campo_id).focus_set()

    def _ruta_completa(self) -> bool:
        """Si hay salida y llegada: sin esto no se puede empezar a grabar."""
        return bool(self._plan_salida) and bool(self._plan_llegada)

    def _parpadear_led_ruta(self) -> None:
        """Verde fijo con el plan completo; rojo parpadeante mientras falte."""
        if self._ruta_completa():
            self.route_led.configure(fg=GREEN)
        else:
            self._route_blink_on = not self._route_blink_on
            self.route_led.configure(fg=RED if self._route_blink_on else BG)
        self.root.after(500, self._parpadear_led_ruta)

    def _tick_automatico(self, state: SimState) -> None:
        """Deja que la máquina de estados decida cuándo grabar.

        Se le pasa el tiempo real transcurrido desde la vuelta anterior, no un
        valor fijo: la ventana puede retrasarse y las confirmaciones (despegue,
        aterrizaje, parada) se cuentan en segundos de reloj.
        """
        ahora = time.monotonic()
        transcurrido = 0.0 if self._ultimo_tick is None else ahora - self._ultimo_tick
        self._ultimo_tick = ahora

        if self.state_machine is None:
            return

        estado_antes = self.state_machine.state.name
        accion, motivo = self.state_machine.update(state, transcurrido)
        estado_ahora = self.state_machine.state.name

        # El cambio de estado es el dato que más falta hacía: sin esto no
        # había forma de saber si el grabador seguía atascado en tierra o si
        # es que la condición de arranque nunca se cumplía.
        if estado_ahora != estado_antes:
            self._apuntar_evento(
                f"{estado_antes} → {estado_ahora}: {self.state_machine.last_reason} "
                f"(GS {state.gs_kt:.1f} kt, "
                f"{'en tierra' if state.on_ground else 'en el aire'})"
            )

        if accion == "empezar_grabacion" and not self._recording:
            if self._ruta_completa():
                self._start()
                self._apuntar_evento("empieza la grabación")
            else:
                motivo = "Falta origen/destino del plan de vuelo — no se graba"
                self._apuntar_evento(
                    "NO se graba: falta el origen o el destino del plan de vuelo"
                )
        elif accion == "parar_grabacion" and self._recording:
            self._stop()
            self._apuntar_evento("grabación detenida")
            # Vuelo cerrado: la máquina queda lista para el siguiente sin
            # tener que reabrir EvA.
            self.state_machine.reset()

        # El motivo se apunta cuando cambia; en pantalla se ve siempre.
        if motivo and motivo != self._ultimo_motivo:
            self._ultimo_motivo = motivo
        self.status_detail.configure(text=motivo)
        self.fase_label.configure(text=estado_ahora)

    def _update_sim_display(self) -> None:
        """Refresca el reloj y los datos del simulador."""
        state = self.poller.latest if self.poller is not None else None

        if state is not None and self.mode_var.get() == MODO_AUTOMATICO:
            try:
                self._tick_automatico(state)
            except Exception as exc:
                # Un fallo aquí no debe parar el refresco de la ventana, pero
                # tampoco puede desaparecer sin dejar rastro.
                debuglog.fallo("modo automatico", exc)
        elif self.mode_var.get() == MODO_MANUAL:
            self._ultimo_tick = None

        self._refresh_tiempo()

        if state is not None and not self._minimized:
            transponder = (
                TRANSPONDER_LABELS.get(state.transponder_state)
                or state.squawk
                or "---"
            )
            self.transponder_label.configure(
                text=(
                    f"ALT: {int(state.alt_msl_ft):05d}ft | "
                    f"GS: {int(state.gs_kt):03d}kt | {transponder}"
                )
            )
            self._update_estado_badges(state)
            self._mostrar_avion(state)
            self._avisar_datos_que_faltan()

        self.root.after(500, self._update_sim_display)

    # -- Bitácora de eventos ------------------------------------------
    # Lo que el grabador va detectando, con su hora. Nació de un problema
    # concreto: durante las pruebas la grabación automática no arrancó y no
    # hubo forma de saber por qué, porque la única pista era una frase que
    # se pisaba a sí misma cada medio segundo. Aquí queda el historial.

    #: Cuántas líneas se guardan. Un vuelo largo no puede comerse la memoria,
    #: y para entender qué pasó sobran las últimas.
    _MAX_EVENTOS = 500

    def _apuntar_evento(self, texto: str) -> None:
        """Añade una línea a la bitácora, con la hora UTC delante."""
        marca = datetime.now(timezone.utc).strftime("%H:%M:%S")
        linea = f"[{marca}Z] {texto}"

        self._eventos.append(linea)
        if len(self._eventos) > self._MAX_EVENTOS:
            del self._eventos[: len(self._eventos) - self._MAX_EVENTOS]

        # Al registro también: si el piloto no tiene la ventana abierta, el
        # rastro no se pierde.
        debuglog.apunte(texto)

        if self._eventos_text is not None:
            try:
                self._eventos_text.configure(state="normal")
                self._eventos_text.insert("end", linea + "\n")
                self._eventos_text.see("end")
                self._eventos_text.configure(state="disabled")
            except tk.TclError:
                # La ventana se cerró entre medias: se sigue guardando en la
                # lista, que es lo que importa.
                self._eventos_text = None

    def _abrir_ventana_eventos(self) -> None:
        """Ventana con la bitácora. Redimensionable, y se puede tener al lado."""
        if self._eventos_window is not None:
            try:
                self._eventos_window.deiconify()
                self._eventos_window.lift()
                return
            except tk.TclError:
                self._eventos_window = None

        ventana = tk.Toplevel(self.root)
        ventana.title("Eventos del vuelo")
        ventana.configure(bg=BG)
        ventana.geometry("560x360")

        marco = tk.Frame(ventana, bg=BG, padx=10, pady=10)
        marco.pack(fill="both", expand=True)

        barra = tk.Scrollbar(marco)
        barra.pack(side="right", fill="y")

        texto = tk.Text(
            marco, bg=PANEL, fg=FG, font=("Consolas", 9), wrap="word",
            relief="flat", yscrollcommand=barra.set,
        )
        texto.pack(side="left", fill="both", expand=True)
        barra.configure(command=texto.yview)

        # Lo ocurrido antes de abrir la ventana también cuenta.
        texto.insert("end", "\n".join(self._eventos) + ("\n" if self._eventos else ""))
        texto.see("end")
        texto.configure(state="disabled")

        def _al_cerrar() -> None:
            self._eventos_text = None
            self._eventos_window = None
            ventana.destroy()

        ventana.protocol("WM_DELETE_WINDOW", _al_cerrar)
        self._eventos_window = ventana
        self._eventos_text = texto

    def _mostrar_avion(self, state: SimState) -> None:
        """Pinta el avión detectado, y lo apunta la primera vez que cambia."""
        avion = state.aircraft_type or "—"
        if state.aircraft_registration:
            avion = f"{avion} · {state.aircraft_registration}"
        self.avion_label.configure(
            text=f"Avión: {avion}",
            fg=FG_DIM if state.aircraft_type else RED,
        )
        if avion != self._ultimo_avion:
            self._ultimo_avion = avion
            if state.aircraft_type:
                self._apuntar_evento(f"avión detectado: {avion}")

    def _avisar_datos_que_faltan(self) -> None:
        """Deja constancia de los datos que el simulador no da.

        El conector ya llevaba esta lista (`missing_variables`) y **nadie la
        miraba**: por eso el transpondedor podía llevar días sin llegar sin
        que nada lo dijera. Se apunta una sola vez por conjunto de datos que
        falten, no en cada vuelta del refresco (medio segundo), que llenaría
        el registro de ruido.
        """
        if self.connector is None:
            return
        # Acumulativo, y solo se apuntan los que aparecen por primera vez.
        #
        # Antes se comparaba con la lista de la vuelta anterior y el registro
        # se llenaba de la misma línea cada segundo: el conector vacía
        # `_missing` al empezar cada consulta y lo va rellenando, así que
        # leerlo desde la interfaz a medias devuelve a veces la lista entera
        # y a veces un trozo. Comparar contra un conjunto que solo crece
        # quita esa carrera de en medio.
        nuevos = sorted(
            set(self.connector.missing_variables) - self._datos_que_faltaban
        )
        if nuevos:
            self._datos_que_faltaban.update(nuevos)
            self._apuntar_evento(
                "el simulador no da estos datos: " + ", ".join(nuevos)
            )

    def _update_estado_badges(self, state: SimState) -> None:
        """Colorea el XPDR y las luces SOP con el estado real del simulador.

        Verde = encendida/en ALT, rojo = apagada, gris = el simulador no
        expone ese dato (no se inventa un color para "no sé").
        """
        if state.transponder_state is not None:
            texto = f"XPDR {TRANSPONDER_LABELS.get(state.transponder_state, '---')}"
            color = GREEN if state.mode_charlie else (
                RED if state.transponder_state == 0 else GREY
            )
            self.xpdr_badge.configure(text=texto, bg=color)
        elif state.squawk:
            # Sin el modo, pero con el código: es lo que hay y vale de algo.
            # `TRANSPONDER STATE` no está en la tabla de python-SimConnect
            # (solo `TRANSPONDER CODE` y `TRANSPONDER AVAILABLE`), así que en
            # la práctica el modo casi nunca llega. Enseñar el squawk es
            # mejor que un "---" que hace pensar que el transpondedor no va.
            self.xpdr_badge.configure(text=f"XPDR {state.squawk}", bg=GREY)
        else:
            self.xpdr_badge.configure(text="XPDR ---", bg=GREY)

        for campo, badge in self._luces_badges.items():
            valor = getattr(state, campo)
            if valor is None:
                badge.configure(bg=GREY)
            else:
                badge.configure(bg=GREEN if valor else RED)

    def _tiempo_grabado(self) -> str:
        """Duración de la grabación en curso, como hh:mm:ss."""
        if self.recorder is None or not self._recording:
            return "00:00:00"
        total = int(self.recorder.elapsed_s)
        horas, resto = divmod(total, 3600)
        minutos, segundos = divmod(resto, 60)
        return f"{horas:02d}:{minutos:02d}:{segundos:02d}"

    def _refresh_tiempo(self) -> None:
        """Pone el reloj en la ventana que esté visible."""
        texto = self._tiempo_grabado()
        if self._minimized:
            if self._led_time is not None:
                self._led_time.configure(text=texto)
        else:
            self.time_label.configure(text=texto)

    def recordings_dir(self) -> Path:
        """Carpeta de grabaciones."""
        if self.settings.carpeta_grabaciones:
            return Path(self.settings.carpeta_grabaciones)
        return paths.recordings_dir()

    def _on_closing(self) -> None:
        """Cierra ordenadamente: primero el vuelo, luego la ventana.

        Si se estaba grabando, se para para que el vuelo quede escrito. Cerrar
        EvA no debe costar el vuelo que se acaba de hacer.
        """
        if self._recording:
            try:
                self._stop()
            except Exception as exc:
                debuglog.fallo("cierre del vuelo al salir", exc)

        self._drop_connection()

        if self._led_window is not None:
            self._led_window.destroy()
        self.root.destroy()


def main() -> None:
    """Punto de entrada."""
    root = tk.Tk()
    EvaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
