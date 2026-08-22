"""Instalador de EvA.

Este fichero se empaqueta como `setup.exe` y es lo único que recibe el
piloto. Al ejecutarlo:

1. Comprueba los requisitos y enseña qué falta.
2. Deja elegir la carpeta de instalación.
3. Copia `eva.exe` (que va incrustado en este propio instalador).
4. Crea la subcarpeta `grabaciones`.
5. Crea accesos directos en el escritorio y en el menú inicio.

Los requisitos que faltan se **avisan pero no bloquean**: alguien puede
instalar EvA antes de tener el simulador puesto. Lo único que impide
continuar es no poder escribir en la carpeta elegida, porque entonces la
instalación no puede hacerse.

Se instala en la carpeta del usuario y no en Archivos de programa a
propósito: así no hace falta permiso de administrador y las grabaciones
pueden guardarse junto al programa, que es donde el piloto las busca.

No depende de ninguna herramienta externa de instalación; se construye con
el mismo PyInstaller que el resto.
"""
from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

# El instalador se empaqueta por separado de la aplicación, así que importa
# el módulo de requisitos por ruta en vez de como parte del paquete.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from avcars import requisitos  # noqa: E402

APP_NAME = "EvA"
EXE_NAME = "eva.exe"
RECORDINGS_DIRNAME = "grabaciones"

BG = "#1b1f24"
PANEL = "#262b32"
FG = "#e8eaed"
FG_DIM = "#9aa3ad"
ACCENT = "#3b82f6"
GREEN = "#12b76a"
AMBER = "#f79009"  # avisos: ni un OK ni un impedimento
RED = "#d92d20"
GREY = "#4a5159"  # el botón de instalar cuando aún no se puede pulsar


def _bundled_dir() -> Path:
    """Carpeta donde PyInstaller ha dejado los ficheros incrustados."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    # Ejecutando el instalador desde el código: los ficheros están en dist/
    return Path(__file__).resolve().parent.parent / "dist"


def default_target() -> Path:
    return Path.home() / APP_NAME


def _create_shortcut(target_exe: Path, shortcut_path: Path, icon: Path) -> bool:
    """Crea un acceso directo de Windows mediante VBScript.

    Se usa VBScript en lugar de pywin32 para no añadir una dependencia solo
    para esto: `wscript` viene con Windows.
    """
    if sys.platform != "win32":
        return False

    import subprocess
    import tempfile

    script = f'''Set s = CreateObject("WScript.Shell")
Set l = s.CreateShortcut("{shortcut_path}")
l.TargetPath = "{target_exe}"
l.WorkingDirectory = "{target_exe.parent}"
l.IconLocation = "{icon}"
l.Description = "EvA - grabador de vuelos"
l.Save
'''
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".vbs", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script)
            vbs = handle.name
        subprocess.run(
            ["wscript", vbs], check=False, creationflags=0x08000000  # sin ventana
        )
        os.unlink(vbs)
        return shortcut_path.exists()
    except Exception:
        return False


def install(target: Path, desktop_shortcut: bool = True) -> tuple[bool, str]:
    """Realiza la instalación. Devuelve (éxito, mensaje)."""
    source_exe = _bundled_dir() / EXE_NAME
    if not source_exe.exists():
        return False, (
            f"El instalador está incompleto: no contiene {EXE_NAME}.\n"
            "Genera primero el ejecutable con tools/build_exe.py."
        )

    try:
        target.mkdir(parents=True, exist_ok=True)
        (target / RECORDINGS_DIRNAME).mkdir(exist_ok=True)

        destination = target / EXE_NAME
        # Si EvA está abierto, Windows no deja sobrescribir el fichero.
        try:
            shutil.copy2(source_exe, destination)
        except PermissionError:
            return False, (
                f"No se ha podido copiar {EXE_NAME} porque el programa está "
                "abierto. Ciérralo y vuelve a intentarlo."
            )
    except OSError as exc:
        return False, f"No se ha podido crear la carpeta de instalación:\n{exc}"

    if desktop_shortcut and sys.platform == "win32":
        desktop = Path(os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"))
        if desktop.exists():
            _create_shortcut(destination, desktop / f"{APP_NAME}.lnk", destination)

        start_menu = (
            Path(os.environ.get("APPDATA", ""))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
        if start_menu.exists():
            _create_shortcut(
                destination, start_menu / f"{APP_NAME}.lnk", destination
            )

    return True, str(target)


class InstallerWindow:
    """Ventana del instalador: requisitos, carpeta y botón de instalar."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.checks: list[requisitos.Resultado] = []
        self._build()
        self._run_checks()

    # -- construcción de la ventana -------------------------------------

    def _build(self) -> None:
        self.root.title(f"Instalar {APP_NAME}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        icon = _bundled_dir() / "EvA.ico"
        try:
            if icon.exists():
                self.root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass

        outer = tk.Frame(self.root, bg=BG, padx=24, pady=20)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer, text=APP_NAME, bg=BG, fg=FG, font=("Segoe UI Semibold", 20)
        ).pack(anchor="w")
        tk.Label(
            outer,
            text="Grabador de vuelos para MSFS y Prepar3D",
            bg=BG,
            fg=FG_DIM,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 14))

        # -- requisitos --
        tk.Label(
            outer, text="Comprobación del equipo", bg=BG, fg=FG_DIM,
            font=("Segoe UI", 8),
        ).pack(anchor="w")

        self.checks_frame = tk.Frame(outer, bg=PANEL)
        self.checks_frame.pack(fill="x", pady=(4, 4))

        self.checks_summary = tk.Label(
            outer, text="", bg=BG, fg=FG_DIM, font=("Segoe UI", 8)
        )
        self.checks_summary.pack(anchor="w", pady=(0, 12))

        # -- carpeta --
        tk.Label(
            outer, text="Se instalará en:", bg=BG, fg=FG_DIM, font=("Segoe UI", 8)
        ).pack(anchor="w")

        row = tk.Frame(outer, bg=BG)
        row.pack(fill="x", pady=(4, 10))

        self.path_var = tk.StringVar(value=str(default_target()))
        tk.Entry(
            row,
            textvariable=self.path_var,
            bg=PANEL,
            fg=FG,
            insertbackground=FG,
            relief="flat",
            font=("Segoe UI", 9),
            width=40,
        ).pack(side="left", ipady=4)

        tk.Button(
            row,
            text="Cambiar",
            command=self._choose,
            bg=PANEL,
            fg=FG,
            activebackground=PANEL,
            activeforeground=FG,
            relief="flat",
            font=("Segoe UI", 8),
            cursor="hand2",
            borderwidth=0,
            padx=10,
        ).pack(side="left", padx=(6, 0), ipady=3)

        self.shortcut_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            outer,
            text="Crear acceso directo en el escritorio",
            variable=self.shortcut_var,
            bg=BG,
            fg=FG_DIM,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 8),
            relief="flat",
            highlightthickness=0,
            cursor="hand2",
        ).pack(anchor="w")

        tk.Label(
            outer,
            text=(
                "Las grabaciones se guardarán en la subcarpeta "
                f"«{RECORDINGS_DIRNAME}» dentro de esa ruta."
            ),
            bg=BG,
            fg=FG_DIM,
            font=("Segoe UI", 8),
            justify="left",
            wraplength=380,
        ).pack(anchor="w", pady=(10, 0))

        self.status = tk.Label(
            outer, text="", bg=BG, fg=FG_DIM, font=("Segoe UI", 8),
            justify="left", wraplength=380,
        )
        self.status.pack(anchor="w", pady=(10, 0))

        self.install_button = tk.Button(
            outer,
            text="INSTALAR",
            command=self._install,
            bg=ACCENT,
            fg="#ffffff",
            activebackground=ACCENT,
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI Semibold", 11),
            pady=8,
            cursor="hand2",
            borderwidth=0,
        )
        self.install_button.pack(fill="x", pady=(14, 0))

    # -- comprobación de requisitos --------------------------------------

    def _run_checks(self) -> None:
        """Comprueba el equipo y pinta el resultado."""
        for widget in self.checks_frame.winfo_children():
            widget.destroy()

        destino = Path(self.path_var.get().strip() or str(default_target()))
        self.checks = requisitos.comprobar_todo(destino)

        symbols = {
            requisitos.Nivel.OK: ("✓", GREEN),
            requisitos.Nivel.AVISO: ("!", AMBER),
            requisitos.Nivel.PROBLEMA: ("✕", RED),
        }

        body = tk.Frame(self.checks_frame, bg=PANEL, padx=10, pady=8)
        body.pack(fill="x")

        for check in self.checks:
            symbol, color = symbols[check.nivel]

            line = tk.Frame(body, bg=PANEL)
            line.pack(fill="x", pady=1)

            tk.Label(
                line, text=symbol, bg=PANEL, fg=color,
                font=("Segoe UI Semibold", 9), width=2,
            ).pack(side="left")
            tk.Label(
                line, text=check.nombre, bg=PANEL, fg=FG,
                font=("Segoe UI", 8), width=18, anchor="w",
            ).pack(side="left")
            tk.Label(
                line, text=check.detalle, bg=PANEL, fg=FG_DIM,
                font=("Segoe UI", 8), anchor="w",
            ).pack(side="left")

            # La solución solo se enseña cuando hace falta.
            if check.solucion and check.nivel is not requisitos.Nivel.OK:
                tk.Label(
                    body,
                    text=check.solucion,
                    bg=PANEL,
                    fg=FG_DIM,
                    font=("Segoe UI", 7),
                    wraplength=360,
                    justify="left",
                ).pack(anchor="w", padx=(26, 0), pady=(0, 4))

        self.checks_summary.configure(text=requisitos.resumen(self.checks))

        # Solo los problemas impiden instalar; los avisos no.
        if requisitos.hay_problemas(self.checks):
            self.install_button.configure(state="disabled", bg=GREY)
            self.status.configure(
                text="Resuelve lo marcado en rojo o elige otra carpeta.", fg=RED
            )
        else:
            self.install_button.configure(state="normal", bg=ACCENT)
            self.status.configure(text="")

    # -- acciones --------------------------------------------------------

    def _choose(self) -> None:
        chosen = filedialog.askdirectory(
            title="Elige dónde instalar EvA", initialdir=str(Path.home())
        )
        if not chosen:
            return

        # Si eligen una carpeta que no se llama EvA, se crea dentro.
        path = Path(chosen)
        if path.name.lower() != APP_NAME.lower():
            path = path / APP_NAME
        self.path_var.set(str(path))
        self._run_checks()

    def _install(self) -> None:
        target = Path(self.path_var.get().strip())
        self.install_button.configure(state="disabled", text="INSTALANDO...")
        self.root.update_idletasks()

        ok, message = install(target, self.shortcut_var.get())

        if ok:
            self.status.configure(text=f"Instalado en {message}", fg=GREEN)
            self.install_button.configure(text="LISTO", bg=GREEN)
            if messagebox.askyesno(
                APP_NAME, "Instalación terminada.\n\n¿Abrir la carpeta?"
            ):
                try:
                    os.startfile(target)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self.root.after(400, self.root.destroy)
        else:
            self.status.configure(text=message, fg=RED)
            self.install_button.configure(state="normal", text="INSTALAR", bg=ACCENT)


def main() -> None:
    root = tk.Tk()
    InstallerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
