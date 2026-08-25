"""AVCARS - cliente de grabación y evaluación de vuelos de la aerolínea virtual."""

#: Versión de EvA Airliner. **Fuente única**: la enseña la ventana, viaja
#: dentro de cada vuelo grabado (`ClientInfo.version`) y es la que se pone
#: en el nombre de la publicación de GitHub. Antes había otra copia en
#: `recorder/flight_log_writer.py` que podía quedarse atrás sin que nadie
#: se enterara.
#:
#: Subirla en cada versión que se reparta a los pilotos: si alguien reporta
#: un fallo, lo primero que hace falta saber es con cuál estaba volando.
__version__ = "2.0.4"
