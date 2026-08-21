# EvA Airliner

Aplicación descargable para grabar vuelos de MSFS/XPlane y sincronizarlos con la plataforma EvA.

## Estructura

```
eva-airliner/
├── caja-negra/          # Vuelos grabados localmente
├── logs/                # Logs de ejecución
└── config.json          # Configuración (callsign, API key, etc.)
```

## Desarrollo

### Requisitos
- Python 3.10+
- MSFS 2024 instalado (solo para conexión SimConnect)

### Instalación

```bash
cd airliner
pip install -r requirements.txt
python app.py
```

### Estructura de Vuelos en Caja Negra

Cada vuelo se guarda como JSON:

```json
{
  "_callsign": "TEST",
  "_guardado_en": "2026-08-21T14:30:00",
  "tipo": "vuelo_msfs",
  "telemetria": {
    "timestamp": "2026-08-21T14:30:00"
  }
}
```

## Build (PyInstaller)

```bash
pip install pyinstaller
python build.py
```

Genera `dist/Airliner.exe`

## Firma de Código (Antivirus)

Para pasar antivirus, firmar con certificado:

```bash
signtool sign /f certificate.pfx /p password /tr http://timestamp.server Airliner.exe
```

## Roadmap

- [ ] Grabación real de telemetría MSFS (SimConnect)
- [ ] Sincronización con EvA web
- [ ] Soporte XPlane (UDP)
- [ ] Interfaz mejorada (Qt/PyQt)
- [ ] Firma de código
- [ ] Instalador MSI
