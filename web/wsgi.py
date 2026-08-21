"""WSGI entry point para deployment en servidores (Gunicorn, Render, Railway, etc).

Uso en producción:
    gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""
import sys
from pathlib import Path

# Agregar client al path para que se pueda importar avcars
RAIZ_REPO = Path(__file__).resolve().parent.parent
CLIENT_DIR = RAIZ_REPO / "client"
sys.path.insert(0, str(CLIENT_DIR))

# Agregar web al path para que se pueda importar los módulos locales
WEB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(WEB_DIR))

from app import app

if __name__ == "__main__":
    app.run()
