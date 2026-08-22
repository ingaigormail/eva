#!/bin/bash
# Comprueba, en un clon limpio de GitHub, que lo que se va a desplegar
# funciona de verdad — no solo "en la carpeta de siempre".
#
#     bash despliegue/probar_pre.sh
#
# Por qué existe: hoy se coló dos veces el mismo fallo — un paquete entero
# que nunca llegó a subirse a git funcionaba perfecto en D:\proyectos\eva
# (los ficheros estaban ahí, en disco, aunque no en git) y reventaba en
# el servidor, que solo tiene lo que hay en GitHub. Python no distingue
# "está en el disco" de "está en git"; este script sí, porque parte de un
# clon nuevo cada vez.
set -euo pipefail

PRE=/d/proyectos/eva-pre
VENV="$PRE/.venv-pre"

echo "--- 1/4  actualizando el clon limpio ---"
cd "$PRE"
git fetch -q origin
ANTES=$(git rev-parse --short HEAD)
git reset -q --hard origin/main
AHORA=$(git rev-parse --short HEAD)
echo "    $ANTES -> $AHORA"

echo "--- 2/4  instalando exactamente lo declarado (nada de lo que ya tengas en tu Python) ---"
[ -d "$VENV" ] || python -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install -q --upgrade pip
"$VENV/Scripts/python.exe" -m pip install -q -e ./client
"$VENV/Scripts/python.exe" -m pip install -q -r ./web/requirements.txt
# pytest no va en requirements.txt a propósito: en producción no hace
# falta y no tiene sentido instalarlo ahí. Aquí sí, para poder probar.
"$VENV/Scripts/python.exe" -m pip install -q pytest

echo "--- 3/4  ¿arranca? (esto es justo lo que reventaba con avcars a medias) ---"
cd web
"$VENV/Scripts/python.exe" -c "
import sys
sys.path.insert(0, '../client'); sys.path.insert(0, '.')
import app
print('    app.py importa y arranca limpio')
"
cd ..

echo "--- 4/4  la batería de tests ---"
export PYTHONPATH="./client;./web"
"$VENV/Scripts/python.exe" -m pytest web/ -q --ignore=web/data 2>&1 | tail -6
"$VENV/Scripts/python.exe" -m pytest client/tests/ -q --ignore=client/tests/test_simconnect_hybrid.py 2>&1 | tail -6

echo ""
echo "=== $AHORA está limpio: puede desplegarse ==="
