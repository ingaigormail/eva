"""La clave con la que Flask firma las cookies de sesión.

Estaba escrita en el código, que vale mientras EvA solo corre en el portátil
del piloto. En un servidor con Internet delante no: quien lea el repositorio
puede firmarse una cookie de sesión de cualquier piloto, administrador
incluido.

De dónde sale, por orden:

1. `EVA_SECRET_KEY` del entorno (lo que usan los hostings serios).
2. `web/data/secret_key.txt`, que se genera solo la primera vez y no va al
   repositorio.

Se genera sola a propósito: si hiciera falta ponerla a mano, alguien acabaría
desplegando con la de ejemplo. Al ser persistente, reiniciar el servidor no
echa a todo el mundo fuera.
"""
from __future__ import annotations

import os
import secrets


def clave_de_sesion() -> str:
    del_entorno = os.environ.get("EVA_SECRET_KEY", "").strip()
    if del_entorno:
        return del_entorno

    from . import cuentas  # import perezoso: cuentas no depende de esto

    path = cuentas.directorio_datos() / "secret_key.txt"
    try:
        guardada = path.read_text(encoding="utf-8").strip()
        if guardada:
            return guardada
    except OSError:
        pass

    nueva = secrets.token_hex(32)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(nueva + "\n", encoding="utf-8")
        # Sin permisos de más: en Linux, solo el dueño.
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        # No se puede escribir (sistema de ficheros de solo lectura): la
        # sesión seguirá funcionando, pero se cerrará al reiniciar.
        pass
    return nueva
