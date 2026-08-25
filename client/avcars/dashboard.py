"""EvA — pantalla de inicio (D1 del esquema de pantallas).

Lanzador de la aplicación: desde aquí se abre el planificador, el registro
de vuelos, la evaluación y vPilot.

Login EvA: usuario (license_id) + contraseña, validados contra el mismo
fichero que la web (`web/data/usuarios.json`). Tras login exitoso se
guarda el ID en settings y se abre el navegador a
http://127.0.0.1:5000/plan (hace falta sesión web aparte).

Dos luces, dos preguntas distintas
-----------------------------------
**vPilot arrancado** y **conectado a VATSIM** no son lo mismo: vPilot puede
llevar un rato abierto sin haberse unido a la red, porque no se conecta
hasta que detecta un simulador de vuelo abierto (confirmado por el usuario,
2026-08-16). Por eso son dos luces independientes, con dos mecanismos
independientes: la de vPilot mira si el proceso está en marcha; la de
VATSIM pregunta a la red.

El CID no se pide
------------------
Se lee solo de la configuración de vPilot (`vPilotConfig.xml`), que ya lo
tiene porque es lo que usa para entrar en la red. Pedírselo al piloto sería
un dato de más. Si ese fichero no aparece —vPilot no está instalado, o está
en un perfil de Windows distinto— se ofrece un campo manual como respaldo,
no como flujo principal.
"""
from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from . import cuentas, paths, sesion_web, settings as settings_module
from .gui import _apply_icon
from .simdetect import is_msfs_running

# Colores: coincidir con web (D2, D6, D7)
BG = "#eef1f6"          # Fondo principal (similar a web)
PANEL = "#ffffff"       # Panel blanco (cards)
FG = "#1e293b"          # Texto oscuro
FG_DIM = "#7c8698"      # Texto tenue
ACCENT = "#2563eb"      # Azul principal
GREEN = "#16a34a"       # Verde (conectado)
GREY = "#9aa3ad"        # Gris (desconectado)
from .vpilot import find_vpilot_executable, is_vpilot_running, read_vpilot_cid

APP_TITLE = "EvA Airliner"
_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO_PATH = _ASSETS / "eva_logo.png"


def _brand_logo(max_width: int, max_height: int) -> Optional[tk.PhotoImage]:
    """Logo actual (PNG) para ventanas claras: el negro del fondo se hace transparente."""
    if not _LOGO_PATH.exists():
        return None
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None

    img = Image.open(_LOGO_PATH).convert("RGBA")
    pixels = img.getdata()
    limpios = []
    for r, g, b, a in pixels:
        if r < 18 and g < 18 and b < 18:
            limpios.append((0, 0, 0, 0))
        else:
            limpios.append((r, g, b, a))
    img.putdata(limpios)
    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img)

#: Consulta de estado de conexión. Pública y sin autenticación; verificada
#: el 2026-08-16: una línea CSV si el CID está conectado, vacío si no.
SLURPER_URL = "https://slurper.vatsim.net/users/info?cid={cid}"

#: La validación del piloto se hace aquí, no en una ventana del escritorio.
URL_LOGIN = "http://127.0.0.1:5000/login"

#: Cada cuánto se pregunta a la Slurper API. Es una llamada mínima, pero es
#: un servicio ajeno y gratuito: 15 s da un LED que reacciona rápido sin
#: martillear a nadie.
POLL_S = 15

#: La comprobación de si vPilot está arrancado es local (mirar procesos, sin
#: red), así que puede ser más frecuente sin coste para nadie más.
VPILOT_POLL_S = 5

#: El servidor de EvA es propio y la llamada es a localhost: 10 s da un LED
#: que reacciona rápido sin ser un sondeo agresivo.
SERVIDOR_POLL_S = 10


def check_servidor_eva(timeout_s: float = 3.0) -> bool:
    """¿Responde el servidor web de EvA ahora mismo?

    No hace falta que esté arriba para **grabar** un vuelo — eso es
    SimConnect en local, sin pasar por la web — pero sí para entrar,
    planificar, subir el vuelo grabado y verlo en la cartilla. Cualquier
    problema de red es simplemente «no disponible»: un LED apagado, nunca
    una excepción en la interfaz.
    """
    try:
        with urllib.request.urlopen(URL_LOGIN, timeout=timeout_s) as response:
            return response.status == 200
    except Exception:
        return False


def check_vatsim_connection(cid: str, timeout_s: float = 5.0) -> Optional[str]:
    """Pregunta a la Slurper API si el CID está conectado.

    Devuelve el indicativo si lo está, None si no. Cualquier problema de red
    también es None: un LED apagado por no poder comprobar es preferible a
    una excepción en la interfaz.
    """
    if not cid:
        return None
    try:
        with urllib.request.urlopen(
            SLURPER_URL.format(cid=cid), timeout=timeout_s
        ) as response:
            text = response.read().decode("utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return None
    fields = text.splitlines()[0].split(",")
    if len(fields) >= 2 and fields[1]:
        return fields[1]
    return None


class LoginWindow:
    """Ventana de login para D1."""

    def __init__(self, root: tk.Tk, callback: Callable[[str], None]):
        self.root = root
        self.callback = callback
        self.root.title("EvA Airliner — Login")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        _apply_icon(self.root)

        marco = tk.Frame(self.root, bg=BG, padx=30, pady=24)
        marco.pack(expand=True)

        self._logo_photo = _brand_logo(320, 96)
        if self._logo_photo is not None:
            tk.Label(marco, image=self._logo_photo, bg=BG).pack(pady=(0, 18))
        else:
            tk.Label(
                marco, text="EvA", bg=BG, fg=FG,
                font=("Segoe UI Semibold", 28)
            ).pack()
            tk.Label(
                marco, text="AIRLINER", bg=BG, fg=ACCENT,
                font=("Segoe UI Semibold", 14)
            ).pack(pady=(0, 20))

        # License ID
        tk.Label(
            marco, text="ID de Piloto", bg=BG, fg=FG,
            font=("Segoe UI", 10)
        ).pack(anchor="w")
        self.license_var = tk.StringVar()
        self.license_entry = tk.Entry(
            marco, textvariable=self.license_var, width=25, bg=PANEL, fg=FG,
            insertbackground=FG, relief="flat", font=("Segoe UI", 10),
        )
        self.license_entry.pack(fill="x", pady=(4, 12))

        # Contraseña
        tk.Label(
            marco, text="Contraseña", bg=BG, fg=FG,
            font=("Segoe UI", 10)
        ).pack(anchor="w")
        self.pass_var = tk.StringVar()
        self.pass_entry = tk.Entry(
            marco, textvariable=self.pass_var, width=25, bg=PANEL, fg=FG,
            insertbackground=FG, relief="flat", font=("Segoe UI", 10),
            show="•"
        )
        self.pass_entry.pack(fill="x", pady=(4, 20))

        # Botón login
        btn = tk.Label(
            marco, text="ENTRAR", bg=ACCENT, fg="white",
            font=("Segoe UI Semibold", 11), pady=8, cursor="hand2"
        )
        btn.pack(fill="x")
        btn.bind("<Button-1>", lambda _: self._login())
        btn.bind("<Enter>", lambda _: btn.configure(bg=ACCENT))
        btn.bind("<Leave>", lambda _: btn.configure(bg=ACCENT))

        # Bind Enter key en el campo de contraseña
        self.pass_entry.bind("<Return>", lambda _: self._login())

        self.error_label = tk.Label(
            marco, text="", bg=BG, fg="#dc2626", font=("Segoe UI", 9)
        )
        self.error_label.pack(pady=(12, 0))

    def _login(self) -> None:
        license_id = self.license_var.get().strip()
        password = self.pass_var.get()
        if not license_id or not password:
            self.error_label.configure(text="Falta ID de piloto y contraseña")
            return
        resultado = cuentas.autenticar_detallado(license_id, password)
        if resultado == cuentas.AUTH_DESCONOCIDO:
            self.error_label.configure(text="Usuario no dado de alta")
            return
        if resultado == cuentas.AUTH_BLOQUEADA:
            self.error_label.configure(text="Cuenta bloqueada. Avisa a un administrador.")
            return
        if resultado != cuentas.AUTH_OK:
            self.error_label.configure(text="Contraseña incorrecta")
            return
        # El ID tal como está dado de alta, no como lo tecleó el piloto.
        self.callback(cuentas.id_canonico(license_id) or license_id)


class DashboardApp:
    """Ventana de inicio: estado de conexión y accesos a las secciones."""

    def __init__(self, root: tk.Tk, license_id: str = "") -> None:
        self.root = root
        self.license_id = license_id  # D1: usuario autenticado
        self.settings = settings_module.load(paths.settings_file())
        self._closing = False
        self._connected_callsign: Optional[str] = None
        self._cid_from_vpilot = False

        # El grabador que hayamos lanzado, para no abrir dos.
        self._grabador: Optional[subprocess.Popen] = None

        # El panel solo necesita saber si el simulador está arrancado, no
        # hablar con él: eso es cosa del grabador (D4).
        self._msfs_connected = False

        # No hace falta para grabar (SimConnect es local), pero sí para
        # entrar, planificar y subir el vuelo — se refleja aparte.
        self._servidor_disponible = False

        self._resolve_cid()
        self._build_ui()
        self._poll_connection()
        self._poll_vpilot_running()
        self._poll_msfs_connection()
        self._poll_servidor()

    # -- CID -------------------------------------------------------------

    def _resolve_cid(self) -> None:
        """Intenta leer el CID de vPilot antes de recurrir al manual.

        Si vPilot lo tiene, prevalece sobre lo que hubiera guardado a mano:
        es la fuente correcta y puede haber cambiado (otra cuenta, otro
        piloto en el mismo PC).
        """
        detectado = read_vpilot_cid()
        if detectado:
            self._cid_from_vpilot = True
            if detectado != self.settings.cid:
                self.settings.cid = detectado
                settings_module.save(self.settings, paths.settings_file())

    # -- interfaz ------------------------------------------------------

    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        _apply_icon(self.root)

        outer = tk.Frame(self.root, bg=BG, padx=20, pady=16)
        outer.pack(fill="both", expand=True)

        # Cabecera con logo
        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x", pady=(0, 10))

        self._logo_photo = _brand_logo(280, 80)
        if self._logo_photo is not None:
            tk.Label(header, image=self._logo_photo, bg=BG).pack(side="left")
        else:
            tk.Label(
                header, text="EvA", bg=BG, fg=FG, font=("Segoe UI Semibold", 28)
            ).pack(side="left")

        # CID: normalmente ni se ve. Solo aparece un campo editable si no se
        # pudo leer de vPilot.
        self.cid_row = tk.Frame(outer, bg=BG)
        self.cid_var = tk.StringVar(value=self.settings.cid)
        if not self._cid_from_vpilot:
            self.cid_row.pack(fill="x", pady=(6, 0))
            tk.Label(
                self.cid_row, text="CID (vPilot no encontrado)", bg=BG, fg=FG_DIM,
                font=("Segoe UI", 8),
            ).pack(side="left")
            self.cid_entry = tk.Entry(
                self.cid_row, textvariable=self.cid_var, width=10, bg=PANEL, fg=FG,
                insertbackground=FG, relief="flat", font=("Consolas", 10),
                justify="center",
            )
            self.cid_entry.pack(side="left", padx=(8, 0), ipady=2)
            self.cid_entry.bind("<Return>", lambda _e: self._save_cid())
            self.cid_entry.bind("<FocusOut>", lambda _e: self._save_cid())

        # Fila de servicios: icono Power arriba, nombre debajo. Las imágenes
        # se guardan en el objeto porque Tk no retiene las suyas: si se van
        # con el recolector, los iconos se quedan en blanco.
        self._power_on = tk.PhotoImage(file=str(_ASSETS / "power_on.png"))
        self._power_off = tk.PhotoImage(file=str(_ASSETS / "power_off.png"))

        servicios = tk.Frame(outer, bg=BG)
        servicios.pack(fill="x", pady=(14, 0))

        self.power_vatsim = self._power_indicator(servicios, "VATSIM")
        self.power_vpilot = self._power_indicator(
            servicios, "VPILOT", on_click=self._launch_vpilot
        )
        self.power_simulador = self._power_indicator(servicios, "SIMULADOR")
        self.power_copilot = self._power_indicator(servicios, "COPILOT")
        self.power_servidor = self._power_indicator(
            servicios,
            "SERVIDOR EVA",
            on_click=lambda: webbrowser.open(URL_LOGIN, new=0),
        )

        # Botones principales: PLAN DE VUELO y GRABAR VUELO
        botones = tk.Frame(outer, bg=BG)
        botones.pack(fill="x", pady=(12, 0))
        self._big_button(botones, "PLAN DE VUELO", self._open_planner)
        self._big_button(botones, "GRABAR VUELO", self._start_recording)

        # Botones secundarios
        botones_sec = tk.Frame(outer, bg=BG)
        botones_sec.pack(fill="x", pady=(0, 0))
        self._big_button(botones_sec, "REGISTRO VUELO", self._open_logbook)
        self._big_button(botones_sec, "EVALUAR VUELO", self._open_evaluation)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Inicializar power buttons
        self._update_power_buttons()

    def _power_indicator(
        self,
        parent: tk.Frame,
        nombre: str,
        on_click: Optional[Callable[[], None]] = None,
    ) -> tk.Label:
        """Icono de encendido con el nombre del servicio debajo.

        Son dos PNG (verde y azul), no un carácter tipográfico: el símbolo
        Unicode de encendido no está en todas las fuentes de Windows, y los
        emojis de círculo traen su propio color y no se dejan teñir.
        """
        columna = tk.Frame(parent, bg=BG)
        columna.pack(side="left", expand=True)

        icono = tk.Label(columna, image=self._power_off, bg=BG)
        icono.pack()

        tk.Label(
            columna, text=nombre, bg=BG, fg=FG, font=("Segoe UI", 8)
        ).pack(pady=(2, 0))

        if on_click is not None:
            icono.configure(cursor="hand2")
            icono.bind("<Button-1>", lambda _e: on_click())

        return icono

    def _set_power(self, icono: tk.Label, encendido: bool) -> None:
        """Verde si el servicio está activo, azul si está apagado."""
        icono.configure(image=self._power_on if encendido else self._power_off)

    def _big_button(
        self, parent: tk.Frame, text: str, command: Callable[[], None]
    ) -> None:
        btn = tk.Label(
            parent, text=text, bg=PANEL, fg=FG,
            font=("Segoe UI Semibold", 11), pady=12, cursor="hand2",
        )
        btn.pack(fill="x", pady=(0, 8))
        btn.bind("<Button-1>", lambda _e: command())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=ACCENT))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=PANEL))

    # -- estado de conexión a VATSIM (red) ------------------------------

    def _save_cid(self) -> None:
        cid = self.cid_var.get().strip()
        if cid != self.settings.cid:
            self.settings.cid = cid
            self.settings.normalizar()
            self.cid_var.set(self.settings.cid)
            settings_module.save(self.settings, paths.settings_file())

    def _poll_connection(self) -> None:
        """Consulta la Slurper API en un hilo para no congelar la ventana."""
        if self._closing:
            return

        def worker() -> None:
            callsign = check_vatsim_connection(self.settings.cid)
            if not self._closing:
                self.root.after(0, lambda: self._show_connection(callsign))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(POLL_S * 1000, self._poll_connection)

    def _show_connection(self, callsign: Optional[str]) -> None:
        self._connected_callsign = callsign
        self._set_power(self.power_vatsim, bool(callsign))

    # -- estado de vPilot (proceso local) -------------------------------

    def _poll_vpilot_running(self) -> None:
        """Comprueba si el proceso de vPilot está en marcha.

        Es una consulta local (lista de procesos), no de red: no hace daño
        a nadie comprobarlo más a menudo que la conexión a VATSIM.
        """
        if self._closing:
            return

        def worker() -> None:
            corriendo = is_vpilot_running()
            if not self._closing:
                self.root.after(0, lambda: self._show_vpilot_running(corriendo))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(VPILOT_POLL_S * 1000, self._poll_vpilot_running)

    def _show_vpilot_running(self, corriendo: bool) -> None:
        self._set_power(self.power_vpilot, corriendo)

    def _poll_msfs_connection(self) -> None:
        """Comprueba periodicamente si MSFS está abierto (cada 15 segundos)."""
        if self._closing:
            return

        self._msfs_connected = is_msfs_running()

        self._update_power_buttons()
        self.root.after(15000, self._poll_msfs_connection)  # Cada 15 segundos

    # -- disponibilidad del servidor de EvA ------------------------------

    def _poll_servidor(self) -> None:
        """Sondea el servidor en un hilo, como VATSIM: es red, aunque local."""
        if self._closing:
            return

        def worker() -> None:
            disponible = check_servidor_eva()
            if not self._closing:
                self.root.after(0, lambda: self._show_servidor(disponible))

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(SERVIDOR_POLL_S * 1000, self._poll_servidor)

    def _show_servidor(self, disponible: bool) -> None:
        self._servidor_disponible = disponible
        self._update_power_buttons()

    # -- actualizar power buttons ----------------------------------------

    def _update_power_buttons(self) -> None:
        """Refresca los cuatro indicadores con el estado que ya se conoce.

        No comprueba nada aquí: cada estado lo actualiza su propio sondeo, que
        corre a su ritmo. Así refrescar la ventana no cuesta consultas.
        """
        self._set_power(self.power_vatsim, bool(self._connected_callsign))
        self._set_power(self.power_simulador, self._msfs_connected)
        self._set_power(self.power_copilot, False)  # aún sin implementar
        self._set_power(self.power_servidor, self._servidor_disponible)

    def _open_web_planner(self) -> None:
        """Abre el navegador a http://127.0.0.1:5000/plan (D2 web)."""
        try:
            webbrowser.open("http://127.0.0.1:5000/plan", new=0)
        except Exception as e:
            messagebox.showwarning(
                APP_TITLE,
                f"No se pudo abrir el navegador:\n{e}",
                parent=self.root
            )

    # -- acciones ------------------------------------------------------

    def _start_recording(self) -> None:
        """D4: Lanza EVA Airliner, el grabador de vuelos (gui.py).

        Con guarda contra el doble arranque: pulsar dos veces abría dos
        grabadores, y dos procesos escribiendo el mismo vuelo se pisan.
        """
        if self._grabador is not None and self._grabador.poll() is None:
            messagebox.showinfo(
                APP_TITLE,
                "EVA Airliner ya está abierto.\n\n"
                "Búscalo en la barra de tareas: solo debe haber uno grabando.",
                parent=self.root,
            )
            return

        try:
            self._grabador = subprocess.Popen(
                [sys.executable, "-m", "client.avcars.gui"],
                cwd=str(Path(__file__).resolve().parent.parent.parent)
            )
        except Exception as e:
            messagebox.showerror(
                APP_TITLE,
                f"No se pudo abrir EVA Airliner.\n\n{str(e)}",
                parent=self.root
            )

    def _open_planner(self) -> None:
        webbrowser.open("http://127.0.0.1:5000/plan", new=0)

    def _open_logbook(self) -> None:
        """D7: Abre registro de vuelos en web."""
        try:
            # `new=0` reutiliza la ventana ya abierta: una sola, como se pidió.
            webbrowser.open("http://127.0.0.1:5000/vuelos", new=0)
        except Exception as e:
            messagebox.showwarning(
                APP_TITLE,
                f"No se pudo abrir el navegador:\n{e}",
                parent=self.root
            )

    def _open_evaluation(self) -> None:
        """D6: Abre evaluación de vuelo en web."""
        try:
            webbrowser.open("http://127.0.0.1:5000/", new=0)
        except Exception as e:
            messagebox.showwarning(
                APP_TITLE,
                f"No se pudo abrir el navegador:\n{e}",
                parent=self.root
            )

    def _launch_vpilot(self) -> None:
        exe = find_vpilot_executable(self.settings.vpilot_path)
        if exe is not None:
            subprocess.Popen([exe], cwd=exe.rsplit("\\", 1)[0])
            return
        self._ask_vpilot_path()

    def _ask_vpilot_path(self) -> None:
        """vPilot no aparece en ninguna ruta habitual: se pide la suya.

        No es solo un aviso — lleva el botón para localizarlo, porque un
        mensaje sin forma de arreglarlo obliga a salir de la app para nada.
        """
        dialogo = tk.Toplevel(self.root)
        dialogo.title(APP_TITLE)
        dialogo.configure(bg=BG)
        dialogo.resizable(False, False)
        dialogo.transient(self.root)
        dialogo.grab_set()

        marco = tk.Frame(dialogo, bg=BG, padx=20, pady=16)
        marco.pack()
        tk.Label(
            marco, text="No se encontró vPilot", bg=BG, fg=FG,
            font=("Segoe UI Semibold", 12),
        ).pack(anchor="w")
        tk.Label(
            marco,
            text="No está en ninguna de las rutas habituales.\n"
                 "Indica dónde está vPilot.exe, o instálalo desde\n"
                 "vpilot.rosscarlson.dev.",
            bg=BG, fg=FG_DIM, font=("Segoe UI", 9), justify="left",
        ).pack(anchor="w", pady=(6, 12))

        def examinar() -> None:
            ruta = filedialog.askopenfilename(
                parent=dialogo, title="Selecciona vPilot.exe",
                filetypes=[("Ejecutable", "*.exe")],
            )
            if not ruta:
                return
            self.settings.vpilot_path = ruta
            settings_module.save(self.settings, paths.settings_file())
            dialogo.destroy()
            subprocess.Popen([ruta], cwd=ruta.rsplit("/", 1)[0].rsplit("\\", 1)[0])

        btn = tk.Label(
            marco, text="EXAMINAR…", bg=PANEL, fg=FG,
            font=("Segoe UI Semibold", 10), pady=8, cursor="hand2",
        )
        btn.pack(fill="x")
        btn.bind("<Button-1>", lambda _e: examinar())
        btn.bind("<Enter>", lambda _e: btn.configure(bg=ACCENT))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=PANEL))

    def _on_close(self) -> None:
        self._closing = True
        self._save_cid()
        self.root.destroy()


class EsperaValidacion:
    """Ventanita que manda al piloto a validarse en la web y espera.

    La validación ya no se hace aquí (decisión del 2026-08-18): se hace en la
    web, con el usuario y la contraseña del piloto. Esta ventana solo abre el
    navegador y espera a que la web anote la sesión.
    """

    def __init__(self, root: tk.Tk, callback: Callable[[str], None]) -> None:
        self.root = root
        self.callback = callback
        self.root.title(f"{APP_TITLE} — Validación")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        marco = tk.Frame(root, bg=BG, padx=28, pady=24)
        marco.pack()

        logo = _brand_logo(240, 90)
        if logo is not None:
            self._logo = logo  # referencia viva: si no, se la lleva el GC
            tk.Label(marco, image=logo, bg=BG).pack(pady=(0, 16))

        tk.Label(
            marco,
            text="Valídate en la web para entrar",
            bg=BG, fg=FG, font=("Segoe UI Semibold", 12),
        ).pack()

        self.aviso = tk.Label(
            marco,
            text="Se ha abierto el navegador con tu login.\n"
                 "En cuanto entres, esta ventana se abrirá sola.",
            bg=BG, fg=FG_DIM, font=("Segoe UI", 9), justify="center",
        )
        self.aviso.pack(pady=(6, 16))

        boton = tk.Label(
            marco,
            text="ABRIR EL LOGIN OTRA VEZ",
            bg=ACCENT, fg="white", font=("Segoe UI Semibold", 10),
            pady=9, cursor="hand2",
        )
        boton.pack(fill="x")
        boton.bind("<Button-1>", lambda _e: self._abrir_login())

        # Una sesión anterior no debe colarse como validación de ahora.
        sesion_web.cerrar()
        self._abrir_login()
        self._esperar()

    def _abrir_login(self) -> None:
        try:
            webbrowser.open(URL_LOGIN, new=0)
        except Exception:
            self.aviso.configure(
                text=f"No se pudo abrir el navegador.\nEntra a mano en {URL_LOGIN}"
            )

    def _esperar(self) -> None:
        sesion = sesion_web.leer()
        if sesion is not None:
            self.callback(str(sesion.get("license_id", "")))
            return
        self.root.after(1000, self._esperar)


def main() -> None:
    login_root = tk.Tk()

    def on_login(license_id: str) -> None:
        # gui.py lo necesita para identificar al piloto en las grabaciones.
        settings = settings_module.load(paths.settings_file())
        settings.license_id = license_id
        settings_module.save(settings, paths.settings_file())

        login_root.destroy()

        dashboard_root = tk.Tk()
        DashboardApp(dashboard_root, license_id=license_id)
        dashboard_root.mainloop()

    EsperaValidacion(login_root, callback=on_login)
    login_root.mainloop()


if __name__ == "__main__":
    main()
