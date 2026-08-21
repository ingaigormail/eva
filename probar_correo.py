#!/usr/bin/env python3
"""Manda un correo de prueba de verdad, para comprobar la configuración.

    python probar_correo.py                 # se lo manda al de gestión
    python probar_correo.py otro@correo.com # o a quien se le diga

Lee la configuración de `web/data/correo.json` o de las variables de entorno,
exactamente igual que hace EvA. **No enseña las claves por pantalla.**
"""
import sys
from pathlib import Path

# La consola de Windows viene en cp1252 y no sabe escribir «✓» ni «✗»: sin
# esto, el script muere al imprimir el resultado en vez de contarlo.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / "client"))

from avcars import correo  # noqa: E402


def oculta(secreto: str) -> str:
    """Enseña lo justo para reconocerla, sin destaparla."""
    if not secreto:
        return "(vacía)"
    if len(secreto) <= 8:
        return "*" * len(secreto)
    return f"{secreto[:4]}…{secreto[-2:]} ({len(secreto)} caracteres)"


cfg = correo.configuracion()

print("Configuración que va a usar EvA")
print("------------------------------")
print(f"  Transporte : {cfg.transporte}   <- 'api' es lo que funciona en Render")
print(f"  Servidor   : {cfg.host}")
print(f"  Usuario    : {oculta(cfg.usuario)}")
print(f"  Clave      : {oculta(cfg.password)}")
print(f"  Remitente  : {cfg.remitente}   <- tiene que estar validado en Mailjet")
print(f"  Gestión    : {cfg.gestion}")
print()

if not correo.configurado():
    print("✗ Falta configuración: sin claves no se puede enviar nada.")
    raise SystemExit(1)

destino = sys.argv[1] if len(sys.argv) > 1 else cfg.gestion
print(f"Enviando un correo de prueba a {destino}…")

try:
    correo.enviar(
        destino,
        "[EvA] Correo de prueba",
        "Si lees esto, el envío de correo de EvA funciona.\n",
    )
except correo.CorreoNoConfigurado as exc:
    print(f"\n✗ Sin configurar: {exc}")
    raise SystemExit(1)
except correo.CorreoNoEnviado as exc:
    print(f"\n✗ El proveedor lo rechazó. Motivo tal cual lo dio:\n\n    {exc}\n")
    print("Los motivos más habituales:")
    print("  · El remitente no está validado en Mailjet.")
    print("  · Las claves están cambiadas (la pública va en usuario).")
    raise SystemExit(1)

print(f"\n✓ Enviado. Mira la bandeja de {destino} (y la carpeta de spam).")
