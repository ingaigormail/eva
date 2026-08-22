"""Lanzador de EvA en desarrollo.

La extensión .pyw hace que Windows lo abra con `pythonw.exe`, sin ventana de
consola: doble clic y aparece directamente la aplicación. Una vez instalada,
el piloto ejecuta `eva.exe` en su lugar.

Como no hay consola donde ver un error, cualquier fallo al arrancar se
muestra en un cuadro de diálogo. Sin esto, un módulo que falte haría que el
doble clic simplemente no hiciera nada.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _show_startup_error(exc: BaseException) -> None:
    detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    message = f"EvA no ha podido arrancar.\n\n{exc}\n"
    if isinstance(exc, ImportError):
        missing = getattr(exc, "name", None) or "una dependencia"
        message = (
            f"EvA no ha podido arrancar: falta el módulo '{missing}'.\n\n"
            "Instala las dependencias abriendo una terminal en esta carpeta "
            "y ejecutando:\n\n    pip install -e .\n"
        )

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("EvA", message + "\n\nDetalle técnico:\n" + detail[-1200:])
        root.destroy()
    except Exception:
        # Si ni siquiera hay tkinter, dejamos rastro en un fichero junto al
        # lanzador: es lo único que el piloto podrá enviarnos.
        log = Path(__file__).parent / "eva_error.txt"
        log.write_text(message + "\n" + detail, encoding="utf-8")


def main() -> None:
    try:
        from avcars.gui import main as run_app
    except BaseException as exc:
        _show_startup_error(exc)
        return

    try:
        run_app()
    except BaseException as exc:
        _show_startup_error(exc)


if __name__ == "__main__":
    main()
