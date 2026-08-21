#!/usr/bin/env python3
"""Verifica si el sistema de correo está configurado correctamente."""
import os
import sys
from pathlib import Path

# Agregar client al path
RAIZ_REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ_REPO / "client"))

from avcars import correo

print("=" * 60)
print("VERIFICACIÓN DE CONFIGURACIÓN DE CORREO")
print("=" * 60)

config = correo.configuracion()
print(f"\n✓ Configuración cargada:")
print(f"  Host         : {config.host}")
print(f"  Puerto       : {config.puerto}")
print(f"  Usuario      : {config.usuario}")
print(f"  Remitente    : {config.remitente}")
print(f"  Gestión      : {config.gestion}")
print(f"  Transporte   : {config.transporte}")
print(f"  Password     : {'*' * 4 if config.password else '(no configurada)'}")

print(f"\n✓ Estado:")
print(f"  Modo memoria : {correo.modo_memoria()}")
print(f"  Configurado  : {correo.configurado()}")

if correo.configurado():
    print("\n✅ Sistema de correo CONFIGURADO - emails se pueden enviar")
else:
    print("\n❌ Sistema de correo NO configurado - emails FALLARÁN")
    print("\nVariables de entorno requeridas:")
    print("  - EVA_SMTP_HOST (o fichero web/data/correo.json)")
    print("  - EVA_SMTP_PORT")
    print("  - EVA_SMTP_USER")
    print("  - EVA_SMTP_PASSWORD")
    print("  - EVA_SMTP_FROM (remitente)")
    print("  - EVA_CORREO_GESTION (gestor)")

print("\n" + "=" * 60)
