# Trae a este PC las copias de seguridad del servidor de EvA.
#
# Por que: la auditoria de seguridad del 2026-08-24 (hallazgo H-10) senalo
# que las copias solo viven en /home/eva/copias, en el MISMO servidor que
# protegen. Si el servidor se pierde entero (disco roto, borrado, un
# compromiso serio), las copias se pierden con el. Esto las trae a un sitio
# distinto sin montar infraestructura nueva (sin cuenta de nube, sin
# credenciales que gestionar): tira de lo que ya genera
# despliegue/copia_seguridad.sh cada noche a las 4:00 en el servidor.
#
# Limitacion conocida y aceptada: depende de que este PC este encendido.
# No es tan robusto como un backend en la nube, pero es infinitamente mejor
# que "solo en el servidor", que es la situacion de la que se partia.
#
# SI CAMBIAS DE PC: esta tarea programada NO viaja sola. Al migrar hay que:
#   1. Copiar ~/.ssh/id_ed25519 (o generar una clave nueva y anadirla a
#      /home/eva/.ssh/authorized_keys en el servidor) al PC nuevo.
#   2. Volver a registrar la tarea programada alli (ver el bloque de
#      Register-ScheduledTask mas abajo).
#   3. Opcional pero recomendable: copiar tambien D:\eva-backups-servidor
#      (el historico ya traido) al PC nuevo, o dejarlo como estaba y que
#      simplemente empiece a acumular desde cero en el nuevo sitio.
# Sin este paso, las copias del servidor siguen haciendose bien (eso corre
# en el propio VPS, es independiente) pero dejan de traerse a ningun sitio
# fuera de el, que es justamente el riesgo que esto intenta tapar.
#
# Instalar como tarea programada (una sola vez, manual):
#   $accion = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\proyectos\eva\despliegue\sync_backups_local.ps1"'
#   $disparador = New-ScheduledTaskTrigger -Daily -At 6:00AM
#   Register-ScheduledTask -TaskName "EvA - copia de backups del servidor" -Action $accion -Trigger $disparador -Description "Trae copias del VPS a este PC"

$ErrorActionPreference = "Stop"

$Servidor = "eva@7c0cdce9-a46a-4339-9df6-50a26f00f11c.clouding.host"
$ClaveSSH = Join-Path $env:USERPROFILE ".ssh\id_ed25519"
$Destino = "D:\eva-backups-servidor"

if (-not (Test-Path $Destino)) {
    New-Item -ItemType Directory -Path $Destino -Force | Out-Null
    icacls $Destino /inheritance:r | Out-Null
    icacls $Destino /grant:r "$($env:USERNAME):(OI)(CI)F" | Out-Null
}

Write-Output ((Get-Date -Format 'yyyy-MM-dd HH:mm') + " trayendo copias de " + $Servidor + "...")

$origen = $Servidor + ":/home/eva/copias/*.gz"
& scp -i $ClaveSSH -o ConnectTimeout=20 -q $origen $Destino

if ($LASTEXITCODE -ne 0) {
    Write-Error ("scp termino con codigo " + $LASTEXITCODE + " - revisar conexion SSH.")
    exit 1
}

$total = (Get-ChildItem $Destino -Filter "*.gz" | Measure-Object).Count
$tamanoMB = "{0:N1}" -f ((Get-ChildItem $Destino -Filter "*.gz" | Measure-Object -Property Length -Sum).Sum / 1MB)
Write-Output ((Get-Date -Format 'yyyy-MM-dd HH:mm') + " listo: " + $total + " ficheros en " + $Destino + " (" + $tamanoMB + " MB)")
