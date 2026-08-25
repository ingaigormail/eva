"""Diario de incidencias para la fase de pruebas.

**Esto es andamio: está pensado para quitarse al pasar a producción.** Cómo
retirarlo, cuando llegue el momento, está al final de este texto.

Por qué existe
--------------
La ventana de EvA se refresca sola cada medio segundo. Si una de esas vueltas
lanza una excepción y se deja subir, Tkinter llena la consola de trazas y la
ventana deja de responder, así que hay varios `except Exception` que se la
tragan a propósito. El problema es que un fallo tragado es un fallo invisible:
durante las pruebas del 17-08-2026 hubo tres bugs escondidos justo ahí (el
plan de vuelo sin `network`, el grabador que nunca arrancaba y `tasklist`
devolviendo `None`), y ninguno dejaba rastro en pantalla.

Este módulo es el rastro. No cambia el comportamiento: lo que se tragaba se
sigue tragando, pero antes queda escrito con su traza completa.

Cómo se apaga
-------------
**Encendido por defecto** mientras EvA esté en pruebas. Estuvo al revés
hasta el 2026-08-24, y salió caro: ese día un vuelo de pruebas falló dos
veces —no arrancó la grabación automática y el cierre dio error— y no quedó
rastro de ninguno de los dos, justo por esto.

Se apaga con la variable de entorno::

    $env:EVA_DEBUG = "0"        # PowerShell

o dejando un fichero vacío llamado `eva.nodebug` junto a `eva.config.json`,
que es más cómodo para el piloto: no hay que tocar la consola.

El fichero se escribe en `eva-debug.log`, junto a la configuración. Se corta
solo al llegar a 2 MB para no comerse el disco en un vuelo largo.

Cómo se quita
-------------
1. Borrar este fichero.
2. Buscar `debuglog` en `client/` y quitar los `debuglog.fallo(...)` que
   aparezcan; son todos llamadas sueltas dentro de bloques `except`, así que
   basta con borrar la línea.
3. Borrar `client/tests/test_debuglog.py`.

No hace falta tocar nada más: ningún otro módulo depende de éste.
"""
from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import paths

NOMBRE_FICHERO = "eva-debug.log"
#: Se conserva por compatibilidad: antes encendía el diario. Hoy el diario
#: está encendido de serie, así que este fichero ya no hace falta (tenerlo
#: no molesta).
NOMBRE_INTERRUPTOR = "eva.debug"
#: El que sí importa ahora: su presencia **apaga** el diario.
NOMBRE_APAGADO = "eva.nodebug"

#: Al llegar aquí se empieza de cero. Un vuelo largo con el simulador dando
#: guerra puede escribir mucho, y el log no debe llenar el disco del piloto.
TAMANO_MAXIMO_BYTES = 2 * 1024 * 1024

#: Se resuelve una vez: consultar el entorno y el disco en cada línea sería
#: caro en un bucle que corre dos veces por segundo.
_activo: Optional[bool] = None


def activo() -> bool:
    """True si el diario está encendido."""
    global _activo
    if _activo is None:
        _activo = _detectar()
    return _activo


def _detectar() -> bool:
    """Encendido salvo que se apague a propósito.

    Estuvo apagado por defecto y salió caro: en las pruebas de vuelo del
    2026-08-24 la grabación automática no arrancó y el cierre del vuelo dio
    error, y **ninguno de los dos dejó rastro** porque el diario no estaba
    puesto. Mientras EvA esté en pruebas, el coste de escribir unas líneas es
    ridículo comparado con perder un vuelo entero de información.

    Se apaga con `EVA_DEBUG=0`, o creando un fichero `eva.nodebug` al lado de
    la configuración para quien no quiera tocar variables de entorno.
    """
    apagado = os.environ.get("EVA_DEBUG", "").strip()
    if apagado == "0":
        return False
    if apagado not in ("",):
        return True
    try:
        return not (paths.base_dir() / NOMBRE_APAGADO).exists()
    except Exception:
        # Ante la duda, encendido: un diario de más no rompe nada; uno de
        # menos deja un fallo sin explicación.
        return True


def reiniciar_deteccion() -> None:
    """Vuelve a mirar si está encendido. Para los tests."""
    global _activo
    _activo = None


def ruta() -> Path:
    """Fichero donde se escribe el diario."""
    return paths.base_dir() / NOMBRE_FICHERO


def apunte(mensaje: str) -> None:
    """Escribe una línea en el diario, si está encendido."""
    if not activo():
        return
    _escribir(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {mensaje}\n")


def fallo(contexto: str, error: Optional[BaseException] = None) -> None:
    """Deja constancia de una excepción que se está tragando.

    Se usa dentro del `except`, sin argumentos si no hace falta el objeto::

        except Exception as exc:
            debuglog.fallo("refresco de la ventana", exc)
    """
    if not activo():
        return

    traza = ""
    try:
        if error is not None:
            traza = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        else:
            traza = traceback.format_exc()
    except Exception:
        traza = "(no se pudo formatear la traza)\n"

    _escribir(
        f"{datetime.now():%Y-%m-%d %H:%M:%S}  FALLO en {contexto}\n"
        f"{traza.rstrip()}\n"
    )


def _escribir(texto: str) -> None:
    """Vuelca al fichero. Nunca lanza: un diario roto no puede tirar EvA."""
    try:
        destino = ruta()
        destino.parent.mkdir(parents=True, exist_ok=True)
        modo = "a"
        if destino.exists() and destino.stat().st_size > TAMANO_MAXIMO_BYTES:
            modo = "w"  # se empieza de cero en vez de crecer sin límite
        with destino.open(modo, encoding="utf-8") as fichero:
            fichero.write(texto)
    except Exception:
        pass  # aquí sí que no queda nadie a quien avisar
