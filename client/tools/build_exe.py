"""Empaqueta EvA en un ejecutable y genera su instalador.

El objetivo es que un piloto pueda usar EvA sin instalar Python ni saber qué
es pip: descarga un fichero, doble clic, y ya está. Esto es lo que hace
posible el requisito de huella local mínima.

Se generan dos cosas:

- `dist/eva.exe`: la aplicación.
- `dist/setup.exe`: el instalador, que lleva la aplicación dentro y la copia
  a la carpeta elegida junto con la carpeta `grabaciones`.

Uso (en Windows, con el entorno del proyecto activo):

    pip install pyinstaller
    python tools/build_exe.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = CLIENT_DIR / "avcars" / "assets"
ICON = ASSETS_DIR / "EvA.ico"
ENTRY = CLIENT_DIR / "eva.pyw"

APP_NAME = "eva"
SETUP_NAME = "setup"


def _ensure_icon() -> None:
    if ICON.exists():
        return
    print("El icono no existe todavía; generándolo...")
    subprocess.run(
        [sys.executable, str(CLIENT_DIR / "tools" / "make_icon.py")], check=True
    )


def _check_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Falta PyInstaller. Instálalo con:\n\n    pip install pyinstaller\n"
        )


def _executable_name(base: str) -> str:
    return f"{base}.exe" if sys.platform == "win32" else base


def _add_data(source: Path, destination: str) -> str:
    """Construye un --add-data con el separador que toca en cada sistema."""
    separator = ";" if sys.platform == "win32" else ":"
    return f"--add-data={source}{separator}{destination}"


def _run_pyinstaller(name: str, entry: Path, extra: list[str]) -> None:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        f"--name={name}",
        "--onefile",   # un solo .exe, sin carpeta de dependencias
        "--windowed",  # sin ventana de consola
        "--clean",
        "--noconfirm",
        f"--icon={ICON}",
        *extra,
        f"--distpath={CLIENT_DIR / 'dist'}",
        f"--workpath={CLIENT_DIR / 'build'}",
        f"--specpath={CLIENT_DIR / 'build'}",
        str(entry),
    ]
    print("  " + " ".join(command) + "\n")
    subprocess.run(command, check=True, cwd=CLIENT_DIR)


def _report(exe: Path) -> None:
    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"  Generado: {exe}  ({size_mb:.1f} MB)")


def main() -> None:
    if sys.platform != "win32":
        print(
            "Aviso: PyInstaller genera un ejecutable para el sistema en el que "
            "se ejecuta. Para obtener un .exe de Windows hay que lanzar este "
            "script en Windows.\n"
        )

    _check_pyinstaller()
    _ensure_icon()

    dist = CLIENT_DIR / "dist"

    print("\n--- 1/2  Aplicación ---\n")
    _run_pyinstaller(
        name=APP_NAME,
        entry=ENTRY,
        # Python-SimConnect incluye SimConnect.dll junto al paquete. Sin
        # --collect-all, PyInstaller solo empaqueta el código Python y el
        # .exe no podría hablar con el simulador.
        extra=["--collect-all=SimConnect", _add_data(ASSETS_DIR, "assets")],
    )

    app_exe = dist / _executable_name(APP_NAME)
    if not app_exe.exists():
        raise SystemExit("PyInstaller no ha generado la aplicación; se detiene aquí.")
    _report(app_exe)

    print("\n--- 2/2  Instalador ---\n")
    # El instalador lleva dentro la aplicación recién construida y el icono,
    # de modo que es el único fichero que hay que repartir.
    _run_pyinstaller(
        name=SETUP_NAME,
        entry=CLIENT_DIR / "tools" / "installer.py",
        extra=[
            _add_data(app_exe, "."),
            _add_data(ICON, "."),
            # El instalador importa avcars.requisitos para comprobar el equipo.
            f"--paths={CLIENT_DIR}",
            "--hidden-import=avcars.requisitos",
        ],
    )

    setup_exe = dist / _executable_name(SETUP_NAME)
    if setup_exe.exists():
        _report(setup_exe)
        print("\nReparte este fichero a los pilotos:")
        print(f"  {setup_exe}")


if __name__ == "__main__":
    main()
