# Configuración de Email en Render

## ⚠️ CRÍTICO: Cambiar Contraseña de Gmail

1. Ir a https://myaccount.google.com/
2. Cambiar la contraseña de `aviacionmsfs@gmail.com`
3. La contraseña de aplicación actual está expuesta - generar una nueva

## Configuración en Render

Para que el email funcione en Render, agregar estas **variables de entorno** en dashboard de Render:

```
EVA_SMTP_HOST=smtp.gmail.com
EVA_SMTP_PORT=587
EVA_SMTP_USER=aviacionmsfs@gmail.com
EVA_SMTP_PASSWORD=<nueva-contraseña-de-aplicacion>
EVA_SMTP_FROM=aviacionmsfs@gmail.com
EVA_CORREO_GESTION=aviacionmsfs@gmail.com
```

## Pasos:

1. **Generar contraseña de aplicación en Google**:
   - https://myaccount.google.com/apppasswords
   - Seleccionar "Mail" y "Windows" (o la plataforma)
   - Copiar la contraseña generada

2. **En Render dashboard**:
   - Ir a Settings → Environment
   - Agregar todas las variables arriba
   - Redeploy

3. **Verificar**:
   - Ir a `/solicitar-alta`
   - Enviar formulario
   - Revisar que el email del gestor se reciba

## Nota Técnica

El archivo `web/data/correo.json` NO está en git (es `.gitignore`) porque contiene credenciales. Render DEBE usar variables de entorno.
