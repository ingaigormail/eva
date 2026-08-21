"""Script para empaquetar Airliner con PyInstaller."""

import PyInstaller.__main__
import sys
from pathlib import Path

# Directorio del proyecto
airliner_dir = Path(__file__).parent
dist_dir = airliner_dir / "dist"

# Argumentos para PyInstaller
args = [
    str(airliner_dir / "app.py"),
    "--name=Airliner",
    "--onefile",
    f"--distpath={dist_dir}",
    "--icon=icon.ico",  # Reemplazar con ruta real del icono
    "--add-data=:.",  # Incluir archivos adicionales si es necesario
    "--windowed",  # Sin ventana de consola
    "--version-file=version.txt",  # Metadatos de versión
]

print(f"Empaquetando Airliner...")
print(f"Args: {args}")

PyInstaller.__main__.run(args)

print(f"\n✓ Airliner empaquetado en: {dist_dir}")
print(f"  Ejecutable: {dist_dir / 'Airliner.exe'}")
