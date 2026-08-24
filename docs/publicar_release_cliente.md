# Publicar una versión nueva de EvA Airliner

Pasos para cada vez que se modifica el cliente de escritorio (`client/`) y hay
que dar una versión nueva a los pilotos. La web apunta siempre a
`releases/latest/download/setup.exe`, así que **publicar una release nueva es
lo único que hace falta** — no se toca código de la web para esto.

## 1. Compilar

```bash
cd client && python tools/build_exe.py
```

Genera dos ficheros en `client/dist/`:

- `eva.exe` — la aplicación sola (no hace falta repartirla, va dentro del instalador).
- `setup.exe` — el instalador, **este es el que se sube**.

Necesita PyInstaller instalado. Si compilar falla por módulos que faltan,
mirar primero en `D:\proyectos\airhispania` (ver `[[project_eva_descarga_cliente]]`
en memoria — el renombrado del proyecto se dejó ficheros de compilación fuera
más de una vez).

## 2. Decidir el número de versión

Versiones ya publicadas: `V1.0.0`, `v1.0.1`, `v1.0.2`. Sube el número de
parche (`v1.0.X`) para arreglos y ajustes del cliente; sube el de minor
(`v1.X.0`) si el cambio afecta a cómo se usa (p. ej. cambia el flujo de
grabación, no solo lo arregla).

## 3. Etiquetar y subir el commit

Con el código ya comiteado y empujado a `main`:

```bash
git tag -a v1.0.X -m "v1.0.X - resumen corto del cambio"
git push origin v1.0.X
```

La etiqueta tiene que existir en GitHub *antes* del paso 4, para poder
elegirla en el desplegable.

## 4. Crear la release en GitHub

Ir a: <https://github.com/ingaigormail/eva/releases/new>

1. **Choose a tag**: elegir la etiqueta ya subida (`v1.0.X`), no escribir una
   nueva ahí — si no existe todavía, este paso 3 se saltó.
2. **Release title**: el mismo nombre, `v1.0.X`.
3. **Describe this release**: dos o tres líneas de qué cambió para el
   piloto (no el mensaje técnico del commit — esto lo lee gente que no toca
   código).
4. **El fichero va abajo del todo**, en el recuadro que dice *"Attach
   binaries by dropping them here or selecting them"* — **nunca** en la caja
   de descripción de arriba, que solo acepta imágenes/documentos y da un
   error confuso si se suelta un `.exe` ahí.
   Arrastrar `client/dist/setup.exe` a ese recuadro.
5. **Publish release.**

En cuanto está publicada, `/descargar` en la web ya sirve la versión nueva
sin tocar nada más (apunta a `releases/latest`).

## Aviso que verá el piloto

Windows dirá **"Windows protegió su PC"** al abrir `setup.exe`, porque no
está firmado (un certificado cuesta ~100 €/año). La página `/descargar` ya
explica que hay que pulsar "Más información" → "Ejecutar de todas formas".
No es un fallo de la release, pasa siempre.
