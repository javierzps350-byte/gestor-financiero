# Gestor Financiero

**Versión 0.1.1** — incluye actualización automática y segura de bases de datos anteriores.

Aplicación de escritorio local para Windows, construida con Python, Tkinter y SQLite. No requiere servidor, nube, GPU ni conexión a Internet para registrar y consultar información.

## Incluye en esta versión

- Registro de ingresos y gastos, con motivo obligatorio.
- Fecha de pago y fecha de registro automática.
- Método de pago y número de voucher opcional.
- Clientes con tarifa mensual e inicio de cobro.
- Historial de tarifas con fecha de vigencia.
- Distribución automática de ingresos a mensualidades cuando se marca la opción correspondiente.
- Pagos parciales, pagos adelantados y abonos a futuros períodos.
- Consulta de cuotas cubiertas, abonos, deuda vencida y pendiente total.
- Evidencias múltiples por movimiento; los archivos se copian al almacenamiento interno de la aplicación.
- Selección manual de archivos recientes de Descargas (últimos 7 días), sin adjuntar automáticamente un archivo ambiguo.
- Búsqueda por persona, motivo, voucher y rango de fechas.
- Exportación CSV compatible con Excel.
- Copias de seguridad de la base SQLite.
- Anulación controlada de movimientos, conservando el registro de auditoría.
- Asistente ligero para consultas escritas; voz local opcional.
- Puente opcional con NEXUS, aislado y desactivado por defecto.

## Actualizar desde 0.1.0 sin perder datos

1. Cierra el programa.
2. Descomprime la versión nueva en la carpeta del proyecto, reemplazando los archivos del programa, pero no elimines la carpeta `data/`.
3. Ejecuta `run_windows.bat` nuevamente.

Al iniciar, el programa detecta columnas faltantes y las agrega sin borrar los clientes ni los movimientos existentes. Antes de modificar una base antigua crea un respaldo `*_antes_actualizacion_*.sqlite3` junto a la base de datos.

## Requisitos

- Windows 10/11 recomendado.
- Python 3.10 o posterior para ejecutar desde el código fuente.
- Tkinter disponible en la instalación de Python.
- El núcleo no instala paquetes externos.

## Ejecutar desde el código fuente

En PowerShell, dentro de la carpeta del proyecto:

```powershell
py --version
py -m tkinter
py -m venv .venv
.\.venv\Scripts\python.exe main.py
```

La base de datos y los comprobantes se guardan en `data/` durante el desarrollo.

## Crear un ejecutable para Windows

1. Instala Python 3.10 o posterior.
2. Abre PowerShell dentro de la carpeta del proyecto.
3. Ejecuta:

```powershell
.\installer\build_windows.ps1
```

El resultado estará en `dist/GestorFinanciero/`. Para generar el instalador Setup.exe, abre `installer/installer_windows.iss` con Inno Setup después de compilar.

La versión empaquetada guarda los datos de usuario en `%LOCALAPPDATA%\GestorFinanciero`, fuera de los archivos de la aplicación, para conservarlos al actualizar.

## Lógica de mensualidades

- El ciclo inicial comienza en la fecha de primer cobro registrada para el cliente.
- El día de cobro se repite cada mes y se ajusta al último día cuando el mes es más corto (por ejemplo, día 31 pasa a 30 o 28/29 cuando corresponde).
- Los ingresos solo afectan las mensualidades cuando se marca expresamente `Aplicar este ingreso a las mensualidades`.
- La distribución cubre primero los períodos abiertos más antiguos. Si sobra dinero, se generan períodos futuros y se asigna el saldo como abono.
- El importe original del movimiento nunca se cambia: se conserva el pago recibido y la distribución se almacena en otra tabla.
- Cambiar una tarifa no reescribe períodos que ya tengan abonos. Las cuotas futuras sin abonos pueden actualizarse a la nueva tarifa.
- Para anular un movimiento se exige un motivo. Sus distribuciones dejan de contar para los saldos.

## Asistente por voz (opcional)

El núcleo funciona sin reconocimiento de voz. Para habilitar la captura de una sola intervención por micrófono:

1. Instala los paquetes opcionales:

```powershell
.\.venv\Scripts\python.exe -m pip install -r installer\requirements_voice.txt
```

2. Descarga un modelo español compatible con Vosk y colócalo en `models/vosk-es/`.
3. Pulsa `Escuchar una vez` en la pestaña Asistente.

No hay escucha permanente. En esta versión el asistente permite consultas por texto o voz; no registra movimientos dictados automáticamente.

## Puente opcional con NEXUS

El programa no importa código de NEXUS y no comparte la base de datos. Para iniciarlo manualmente:

```powershell
.\installer\run_bridge.ps1
```

El puente escucha exclusivamente en `127.0.0.1:8765`, genera un token y lo guarda en `data/nexus_bridge.token`. No se inicia solo y no se expone a la red local en esta versión. Los registros por API requieren `confirm: true`.

Endpoints disponibles:

- `GET /health` (estado básico, sin datos financieros).
- `GET /api/v1/search?q=texto` (requiere `Authorization: Bearer TOKEN`).
- `GET /api/v1/clients` (requiere token).
- `GET /api/v1/recent-downloads` (requiere token; lista los archivos recientes de Descargas).
- `POST /api/v1/debt` (requiere `client_id` y token).
- `POST /api/v1/evidence` (requiere `movement_id`, `source_path` dentro de Descargas y `confirm: true`).
- `POST /api/v1/movements` (requiere token y `confirm: true`).

## Almacenamiento y copias

- En modo desarrollo: `data/` y `logs/` dentro del proyecto.
- En la aplicación empaquetada: `%LOCALAPPDATA%\GestorFinanciero\`.
- Se recomienda guardar copias adicionales en otro disco o unidad externa. La copia interna no sustituye una copia externa.

## Limitaciones de esta primera versión

- La interfaz está en una primera versión funcional y no incluye todavía edición directa de movimientos; se puede anular con motivo y registrar el movimiento corregido.
- No hay OCR automático de comprobantes ni lectura automática de transferencias de Descargas.
- El asistente de voz solo consulta; no crea registros por dictado.
- La conexión remota desde iPhone y el gestor inteligente de hardware se desarrollarán después de medir el consumo real.
- Los CSV se abren con Excel; la exportación XLSX/PDF se incorporará como módulo opcional.

## Seguridad

El programa guarda información financiera localmente. Protege la cuenta de Windows y el equipo con contraseña, conserva copias de seguridad cifradas fuera del dispositivo cuando sea posible y no compartas la carpeta de datos ni el token del puente.
