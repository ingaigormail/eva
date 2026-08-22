#!/bin/bash
# Copia diaria de EvA: la base de datos y los vuelos de los pilotos.
#
# La base se copia con el comando propio de SQLite, no con `cp`: copiar el
# fichero mientras alguien escribe deja una copia corrupta que solo se
# descubre el día que hace falta restaurarla.
set -euo pipefail

DESTINO=/home/eva/copias
DATOS=/home/eva/eva/web/data
VUELOS=/home/eva/EvA/grabaciones
HOY=$(date +%Y-%m-%d)
DIAS_A_GUARDAR=30

mkdir -p "$DESTINO"

# --- Base de datos (cuentas, solicitudes, planes, resumen de vuelos) ---
if [ -f "$DATOS/eva.db" ]; then
    sqlite3 "$DATOS/eva.db" ".backup '$DESTINO/eva-$HOY.db'"
    gzip -f "$DESTINO/eva-$HOY.db"
fi

# --- Vuelos subidos por los pilotos ---
if [ -d "$VUELOS" ] && [ -n "$(ls -A "$VUELOS" 2>/dev/null)" ]; then
    tar czf "$DESTINO/vuelos-$HOY.tar.gz" -C "$(dirname "$VUELOS")" "$(basename "$VUELOS")"
fi

# --- Configuración que no está en el repositorio y no se puede regenerar ---
tar czf "$DESTINO/config-$HOY.tar.gz" \
    -C /home/eva eva.env \
    $([ -f "$DATOS/correo.json" ] && echo "-C $DATOS correo.json") \
    2>/dev/null || true

# --- Tirar lo viejo, o el disco se llena y el servidor deja de funcionar ---
find "$DESTINO" -name "*.gz" -mtime +$DIAS_A_GUARDAR -delete

echo "$(date '+%Y-%m-%d %H:%M') copia hecha: $(ls -1 "$DESTINO" | wc -l) ficheros, $(du -sh "$DESTINO" | cut -f1)"
