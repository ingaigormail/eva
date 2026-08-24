# El servidor de EvA

EvA corre en un VPS propio, no en Render. El motivo está en la bitácora: el
plan gratuito de Render **borraba la base de datos y los vuelos en cada
despliegue** (disco efímero) y **bloqueaba los puertos de SMTP**. Un VPS con
disco de verdad quita los dos problemas de raíz en vez de esquivarlos.

## Dónde está

- **Web**: https://7c0cdce9-a46a-4339-9df6-50a26f00f11c.clouding.host
- **Proveedor**: Clouding.io (España) · Ubuntu 24.04 LTS
- **Entrar**: `ssh eva@7c0cdce9-a46a-4339-9df6-50a26f00f11c.clouding.host`

Solo se entra **con clave SSH**: el acceso por contraseña y el de root están
cerrados. Un servidor público con contraseña recibe ataques de fuerza bruta
desde el primer día.

## Cómo se actualiza

    ssh eva@<servidor> ./desplegar.sh

Hace copia antes de tocar nada y **comprueba que la versión nueva arranca
antes de reiniciar**: si viene rota, la web sigue en pie con la versión
anterior y te dice cómo volver atrás.

## Qué hay montado

| Pieza | Dónde |
|---|---|
| La aplicación | `/home/eva/eva` (clon de GitHub) |
| Python | `/home/eva/venv` |
| Servicio | `eva.service` — arranca sola al reiniciar, 2 procesos |
| Base de datos | `/home/eva/eva/web/data/eva.db` |
| Vuelos subidos | `/home/eva/EvA/grabaciones` |
| Secretos | `/home/eva/eva.env` (**no está en git**) |
| Copias | `/home/eva/copias` — diarias a las 4:00, 30 días |

Dos procesos y no cuatro: cada uno carga pandas y numpy, que pesan. Para el
volumen de EvA sobra, y deja memoria al resto del sistema.

## Lo que se guarda de cada vuelo

El `.avlog.json` que sube el piloto se guarda **entero y sin tocar**. La
tabla `vuelos_resumen` solo tiene unos 20 campos extraídos, para que la
cartilla vaya rápida sin abrir cientos de ficheros. Es una caché, no la
fuente: cualquier estadística nueva se puede recalcular de los originales.

## Cosas que hay que saber

**La cuenta `pruebas`.** EvA crea sola un `pruebas`/`pruebas` con rol de
administrador para que nadie se quede fuera. En un servidor público eso es
una puerta abierta: aquí se degradó y bloqueó nada más instalar. **Si algún
día se rehace el servidor, hay que volver a cerrarla.**

**El correo va por la API de Gmail**, no por SMTP. Las credenciales están en
`eva.env`. Ver `docs/RENDER_SETUP_EMAIL.md` para el porqué.

**Certificado HTTPS**: Let's Encrypt, se renueva solo (`certbot.timer`).

**`eva.service` está versionado en `despliegue/eva.service`**, copia exacta
de lo que hay en `/etc/systemd/system/eva.service` en el servidor. Lleva
`NoNewPrivileges=true` y `ProtectHome=read-only`: un proceso comprometido
dentro de gunicorn no puede usar `sudo` ni tocar `~/.ssh`, aunque el usuario
`eva` tenga privilegios a nivel de sistema.

**El `sudo` de `eva` está restringido** (`despliegue/eva-sudoers`, instalado
como `/etc/sudoers.d/eva`): solo los comandos concretos que hacen falta
(reiniciar/consultar el servicio, recargar nginx, reiniciar la máquina), no
`ALL=(ALL) NOPASSWD:ALL`. Si algún día hace falta un comando nuevo bajo
`sudo`, se añade explícitamente a ese fichero — no se vuelve a abrir todo.

## Mantenimiento

Poco: los parches de seguridad se aplican solos. Una vez al mes está bien
mirar que el disco no se llene (`df -h`) — es lo más justo de esta máquina.

Auditoría de seguridad completa (con verificación en vivo): ver el historial
de conversación del 2026-08-24 — hallazgos H-01 a H-15, todos cerrados o con
plan salvo H-06 (MFA, pendiente de diseño) y H-07 (decisión de producto, no
de seguridad del servidor).
