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
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox
from typing import Optional

from . import debuglog, paths, settings as settings_module, timing
from .connectors.base import TRANSPONDER_LABELS, SimState
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
URL_CARTILLA = "http://127.0.0.1:5000/registro"

# Colores claros (coherencia con web D2/D6/D7)
BG = "#eef1f6"
PANEL = "#ffffff"
FG = "#1e293b"
FG_DIM = "#7c8698"
ACCENT = "#2563eb"
RED = "#dc2626"
GREEN = "#16a34a"
GREY = "#9ca3af"


def _apply_icon(root: tk.Tk) -> None:
    """Intenta aplicar el icono de EvA a la ventana."""
    try:
        ico = paths.assets_dir() / "eva.ico"
        if ico.exists():
            root.iconbitmap(str(ico))
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
        self.root.title(APP_NAME)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        _apply_icon(self.root)

        # Ventana siempre al frente
        self.root.attributes("-topmost", True)

        self.settings = settings_module.load(paths.settings_file())

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
        self._poll_status()
        self._update_sim_display()

    def _build_ui(self) -> None:
        """Construye la interfaz."""
        pilot_id = self.settings.license_id or "PILOT"

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(padx=16, pady=16)

        # Cabecera: LED MSFS + pilot ID
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 12))

        # LED MSFS (verde/rojo)
        self.led_msfs = tk.Label(
            header,
            text="●",
            bg=BG,
            fg=GREY,
            font=("Segoe UI", 16)
        )
        self.led_msfs.pack(side="left", padx=(0, 8))

        tk.Label(
            header,
            text=pilot_id,
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 12)
        ).pack(side="left")

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

        self.transponder_label = tk.Label(
            inner,
            text="ALT: -----ft | GS: ---kt | ---",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 8)
        )
        self.transponder_label.pack(pady=(8, 0))

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

        # Boton Minimizar
        links = tk.Frame(outer, bg=BG)
        links.pack(fill="x", pady=(8, 0))

        self._minimize_button = tk.Label(
            links,
            text="minimizar",
            bg=BG,
            fg=FG_DIM,
            font=("Segoe UI", 7, "underline"),
            cursor="hand2"
        )
        self._minimize_button.pack(side="left")
        self._minimize_button.bind("<Button-1>", lambda _e: self._minimize())

        self._set_status()

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
        # Obtener tipo de avión del simulador si está disponible
        aircraft_type = None
        if self.poller and self.poller.reading:
            aircraft_type = getattr(self.poller.reading.state, 'aircraft_type', None)

        return FlightPlanInfo(
            rules="VFR",
            departure_icao=self.settings.salida,
            arrival_icao=self.settings.llegada,
            alternate_icao=None,
            route=None,
            aircraft_icao_type=aircraft_type,
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

    def _abrir_cartilla(self) -> None:
        """Abre la cartilla del piloto en el navegador."""
        try:
            webbrowser.open(URL_CARTILLA, new=2)
            debuglog.apunte(f"abierta la cartilla: {URL_CARTILLA}")
        except Exception as exc:
            debuglog.fallo("apertura de la cartilla", exc)
            messagebox.showwarning(
                APP_NAME,
                "No se pudo abrir el navegador con tu cartilla.\n\n"
                f"Ábrela a mano en: {URL_CARTILLA}",
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
            self._set_button_idle()

        # Cada 5 s: es un vistazo a la lista de procesos, no hace falta más.
        self.root.after(5000, self._poll_status)

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

        accion, motivo = self.state_machine.update(state, transcurrido)

        if accion == "empezar_grabacion" and not self._recording:
            self._start()
        elif accion == "parar_grabacion" and self._recording:
            self._stop()
            # Vuelo cerrado: la máquina queda lista para el siguiente sin
            # tener que reabrir EvA.
            self.state_machine.reset()

        self.status_detail.configure(text=motivo)

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
            transponder = TRANSPONDER_LABELS.get(state.transponder_state, "---")
            self.transponder_label.configure(
                text=(
                    f"ALT: {int(state.alt_msl_ft):05d}ft | "
                    f"GS: {int(state.gs_kt):03d}kt | {transponder}"
                )
            )

        self.root.after(500, self._update_sim_display)

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
