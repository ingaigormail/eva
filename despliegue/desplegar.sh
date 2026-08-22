#!/bin/bash
# Actualiza EvA a la última versión de GitHub.
#
#     ssh eva@<servidor> ./desplegar.sh
#
# Hace copia antes de tocar nada: si la versión nueva viene rota, se puede
# volver atrás sin haber perdido las cuentas ni los vuelos.
set -euo pipefail

REPO=/home/eva/eva
VENV=/home/eva/venv

echo "--- copia de seguridad previa ---"
/home/eva/copia_seguridad.sh

echo "--- descargando la versión nueva ---"
cd "$REPO"
ANTES=$(git rev-parse --short HEAD)
git pull -q
AHORA=$(git rev-parse --short HEAD)

if [ "$ANTES" = "$AHORA" ]; then
    echo "    ya estaba al día ($AHORA); no se toca el servicio"
    exit 0
fi
echo "    $ANTES -> $AHORA"

echo "--- dependencias ---"
"$VENV/bin/pip" install -q -e ./client
"$VENV/bin/pip" install -q -r ./web/requirements.txt

echo "--- comprobando que la versión nueva arranca ANTES de reiniciar ---"
# Si esto falla, el servicio viejo sigue en pie y la web no se cae.
cd "$REPO/web"
if ! "$VENV/bin/python" -c "import sys; sys.path.insert(0,'../client'); sys.path.insert(0,'.'); import app" 2>/tmp/eva_fallo.txt; then
    echo "    LA VERSIÓN NUEVA NO ARRANCA. No se reinicia nada."
    cat /tmp/eva_fallo.txt
    echo "    Para volver atrás:  cd $REPO && git reset --hard $ANTES"
    exit 1
fi

echo "--- reiniciando ---"
sudo systemctl restart eva
sleep 4

if curl -sf -o /dev/null http://127.0.0.1:8000/login; then
    echo "listo: EvA responde en la versión $AHORA"
else
    echo "AVISO: el servicio no responde. Registro:"
    sudo journalctl -u eva -n 20 --no-pager
    exit 1
fi
