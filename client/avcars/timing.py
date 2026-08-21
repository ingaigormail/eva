"""Todos los tiempos de EvA, en un solo sitio y coordinados entre sí.

Por qué existe este módulo
--------------------------
Los tiempos estaban repartidos por cinco ficheros y no encajaban. El caso
más claro: los datos congelados se detectaban a los 8 segundos, pero la
máquina de estados confirmaba un aterrizaje a los 5. Con el simulador
congelado, la máquina decidía antes de que nadie se diera cuenta de que los
datos no eran de fiar.

Aquí todo se deriva de una única cadencia base y las relaciones entre
tiempos se comprueban al importar el módulo, de forma que una combinación
incoherente falla en los tests y no en un vuelo real.

La cadena de decisión, de más rápido a más lento
-----------------------------------------------

    refresco de la ventana        0,25 s   se ve fluido
    consulta al simulador         1 s      cadencia base
    detección de datos congelados 4 s      antes que cualquier decisión
    confirmación de despegue      3 s      un bache en pista no cuenta
    confirmación de aterrizaje    5 s      un rebote no cierra el vuelo
    umbral de pausa               6 s      no confundir lentitud con pausa
    confirmación de parada       10 s      el avión ya no va a despegar
    volcado a disco              30 s      lo que se pierde si EvA se cierra
    pausa preocupante            60 s      esto ya no parece una pausa

La regla que ordena todo: **detectar que los datos no sirven tiene que ser
más rápido que cualquier decisión tomada con esos datos**.
"""
from __future__ import annotations

# -- cadencia base ------------------------------------------------------

#: Cada cuánto se consulta al simulador. Todo lo demás se expresa en
#: múltiplos de esto. Subirlo hace a EvA más ligera y más lenta de reflejos;
#: bajarlo carga al simulador sin ganar precisión real, porque las variables
#: de SimConnect tampoco se actualizan mucho más rápido.
POLL_INTERVAL_S = 1.0

#: Refresco de la ventana. Más rápido que la cadencia base para que el
#: contador de tiempo avance con naturalidad y no a saltos de un segundo.
UI_REFRESH_S = 0.25


# -- salud de la conexión -----------------------------------------------

#: Lecturas idénticas consecutivas tras las que se considera que el
#: simulador no está actualizando nada.
#: Cuatro segundos: menos que la confirmación de despegue (3 s) sería
#: demasiado nervioso, y más que la de aterrizaje (5 s) llegaría tarde.
FROZEN_READS = 4

#: Segundos sin datos nuevos tras los que se da la conexión por perdida.
CONNECTION_LOST_S = 10.0


# -- máquina de estados -------------------------------------------------

#: Sin contacto con el suelo durante este tiempo = ha despegado de verdad.
#: Un bache en pista levanta el avión menos de un segundo.
CONFIRM_LIFTOFF_S = 3.0

#: Contacto continuo con el suelo durante este tiempo = ha aterrizado de
#: verdad. Un rebote típico devuelve el avión al aire en 1-2 segundos.
CONFIRM_LANDING_S = 5.0

#: Por debajo del umbral de velocidad durante este tiempo = el vuelo ha
#: terminado. Da margen para salir de pista y rodar un poco.
CONFIRM_STOPPED_S = 10.0

#: Altura sobre el terreno a partir de la cual se acepta que está volando.
CONFIRM_LIFTOFF_AGL_FT = 50.0


# -- pausas del simulador -----------------------------------------------

#: Hueco entre lecturas a partir del cual se sospecha una pausa.
#: Seis segundos = seis ciclos perdidos. Antes estaba en 3 s y la lentitud
#: del cliente (3,1 s por consulta) llenaba el log de pausas inventadas.
PAUSE_GAP_S = 6.0

#: Una pausa más larga que esto probablemente no es una pausa: el simulador
#: está en un menú, se ha perdido la conexión o el equipo está saturado.
PAUSE_SUSPICIOUS_S = 60.0


# -- grabación ----------------------------------------------------------

#: Cada cuánto se vuelca lo grabado al fichero parcial. Es lo máximo que se
#: pierde si EvA se cierra de golpe.
AUTOSAVE_INTERVAL_S = 30.0

#: Muestreo adaptativo: cerca del suelo pasan cosas rápido (rotación, flare,
#: toma); en crucero no pasa nada durante horas.
SAMPLE_NEAR_GROUND_S = 1.0
SAMPLE_CRUISE_S = 10.0
NEAR_GROUND_AGL_FT = 1500.0


# -- coherencia ---------------------------------------------------------


def _check_coherence() -> None:
    """Comprueba que los tiempos encajan entre sí.

    Se ejecuta al importar: una combinación incoherente rompe los tests en
    vez de producir un vuelo mal grabado.
    """
    # La ventana tiene que refrescarse más a menudo que la cadencia base, o
    # el contador daría saltos.
    assert UI_REFRESH_S < POLL_INTERVAL_S, "la ventana va más lenta que el muestreo"

    # Detectar datos congelados debe ocurrir ANTES de que la máquina de
    # estados confirme un aterrizaje con esos mismos datos. Esta es la
    # incoherencia que motivó este módulo.
    frozen_after_s = FROZEN_READS * POLL_INTERVAL_S
    assert frozen_after_s <= CONFIRM_LANDING_S, (
        "los datos congelados se detectarían después de confirmar un "
        "aterrizaje, así que se decidiría con datos que ya sabemos malos"
    )

    # Con muestreo de 1 s hacen falta varios ciclos perdidos para hablar de
    # pausa; si no, cualquier lentitud puntual cuenta como pausa.
    assert PAUSE_GAP_S >= 4 * POLL_INTERVAL_S, (
        "el umbral de pausa está tan cerca del muestreo que la lentitud "
        "normal se confundiría con una pausa"
    )

    # Cerrar el vuelo tiene que ser lo más lento de todo: es la decisión
    # irreversible.
    assert CONFIRM_STOPPED_S > CONFIRM_LANDING_S > CONFIRM_LIFTOFF_S, (
        "el orden de las confirmaciones no va de menos a más comprometido"
    )

    # No tiene sentido volcar a disco más a menudo que el muestreo, ni tan
    # poco que se pierda medio vuelo.
    assert POLL_INTERVAL_S < AUTOSAVE_INTERVAL_S <= 120.0

    # En crucero se guarda menos, nunca más, que cerca del suelo.
    assert SAMPLE_CRUISE_S > SAMPLE_NEAR_GROUND_S >= POLL_INTERVAL_S

    assert PAUSE_SUSPICIOUS_S > PAUSE_GAP_S


_check_coherence()


def resumen() -> str:
    """Descripción de la cadena de tiempos, para diagnóstico."""
    return "\n".join(
        [
            f"consulta al simulador   {POLL_INTERVAL_S:5.2f} s",
            f"refresco de ventana     {UI_REFRESH_S:5.2f} s",
            f"datos congelados        {FROZEN_READS * POLL_INTERVAL_S:5.2f} s",
            f"confirmar despegue      {CONFIRM_LIFTOFF_S:5.2f} s",
            f"confirmar aterrizaje    {CONFIRM_LANDING_S:5.2f} s",
            f"umbral de pausa         {PAUSE_GAP_S:5.2f} s",
            f"confirmar parada        {CONFIRM_STOPPED_S:5.2f} s",
            f"volcado a disco         {AUTOSAVE_INTERVAL_S:5.2f} s",
            f"pausa sospechosa        {PAUSE_SUSPICIOUS_S:5.2f} s",
        ]
    )
