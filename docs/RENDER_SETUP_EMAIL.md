# Configuración del correo en Render

## Lo primero: en Render el SMTP no funciona

Render **bloquea el tráfico saliente a los puertos SMTP (25, 465 y 587) en el plan
gratuito** desde septiembre de 2025, para frenar el spam:
<https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports>

El síntoma en los logs es este, y despista mucho porque parece un problema de EvA:

```
WARNING in app: Enlace de contraseña no enviado: [Errno 101] Network is unreachable
```

No es la contraseña, ni la configuración, ni Gmail. Es que el contenedor no puede
salir por ese puerto. **Da igual cuántas veces se revisen las credenciales.**

En **local** el SMTP sigue funcionando con normalidad. Esto solo afecta al desplegado.

## La salida: Mailjet por API (HTTPS)

`client/avcars/correo.py` trae dos transportes. El `api` habla con la Send API v3.1
de Mailjet por HTTPS (puerto 443), que Render no bloquea. No hay que tocar código:
es todo configuración.

De regalo, la API dice **por qué** rechaza un envío. El SMTP contesta `250 OK` y se
traga el mensaje aunque no lo mande — así se perdió una tarde el 2026-08-18.

### 1. En Mailjet

1. Cuenta gratuita en <https://www.mailjet.com/> (200 correos/día, 6.000/mes).
2. **Validar el remitente**: Account Settings → Sender domains & addresses → Add sender.
   Llega un correo de confirmación. **Sin esto Mailjet rechaza todos los envíos.**
3. Copiar las claves en Account Settings → API Key Management: hay una
   **API Key (pública)** y una **Secret Key (privada)**.

### 2. En Render → Settings → Environment

| Variable | Valor |
|---|---|
| `EVA_CORREO_TRANSPORTE` | `api` |
| `EVA_SMTP_USER` | La API Key **pública** |
| `EVA_SMTP_PASSWORD` | La Secret Key **privada** |
| `EVA_SMTP_FROM` | El remitente validado en el paso 2 |
| `EVA_CORREO_GESTION` | Quien recibe las solicitudes de alta |
| `EVA_SMTP_HOST` | `in-v3.mailjet.com` |

⚠️ **Cuidado con el orden de prioridad**: `EVA_SMTP_USER` y `EVA_SMTP_PASSWORD`
**pisan** a `MJ_APIKEY_PUBLIC` y `MJ_APIKEY_PRIVATE`. Si ya existen con valores de
Gmail, hay que **cambiarles el valor**; añadir las `MJ_*` al lado no sirve de nada,
porque ganan las primeras y el envío sigue fallando.

Después, **Redeploy**.

### 3. Comprobar

Enviar el formulario de `/solicitar-alta` y mirar los logs de Render. Si algo falla,
ahora el motivo sale escrito (cuenta bloqueada, remitente sin validar…), no un
`Network is unreachable` mudo.

## La otra opción: pagar Render

Cualquier plan de pago (~7 $/mes) desbloquea los puertos 465 y 587, y entonces la
configuración de Gmail de toda la vida vuelve a funcionar sin tocar nada. De paso
evita que el servicio se duerma por inactividad. El puerto 25 sigue bloqueado
siempre, también en los planes de pago.

## Nota sobre las credenciales

`web/data/correo.json` **no está en git** a propósito: lleva contraseñas. Por eso
Render no lo recibe y **hay que usar variables de entorno**. En local ese fichero
es lo cómodo; las variables de entorno lo pisan si están puestas.
