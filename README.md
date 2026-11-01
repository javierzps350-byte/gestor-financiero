# Gestor Financiero

**Versión 0.2.1** — incorpora un agente financiero local para consultar y administrar el programa mediante instrucciones escritas o, con el módulo opcional, por voz.

Aplicación de escritorio local para Windows, construida con Python, Tkinter y SQLite. No requiere servidor, nube, GPU ni conexión a Internet para registrar y consultar información.

## Incluye en esta versión

- Interfaz depurada con navegación lateral de texto, sin iconos decorativos.
- Se eliminaron etiquetas de estado, mensajes promocionales y textos técnicos redundantes de la pantalla principal.
- Cabecera simplificada y mayor espacio para el contenido.
- Tarjetas financieras con jerarquía tipográfica más clara y colores discretos.
- Transiciones suaves entre secciones y animación breve de los importes.
- Botones de acciones rápidas con estados visuales al pasar el cursor.

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
- Recalcula las mensualidades cuando se registra un pago atrasado o se anula uno anterior, respetando la fecha real de cada pago.
- Consultas históricas que excluyen pagos cuya fecha sea posterior a la fecha consultada.
- Historial de pagos por cliente, separando importe recibido, importe aplicado a cuotas y parte no aplicada.
- Advertencia ante números de voucher repetidos; permite continuar cuando la repetición es legítima.
- Agente financiero ligero con consultas de ingresos, gastos, balance, clientes, deudas y vouchers.
- Preparación de ingresos, gastos, clientes y cambios de tarifa mediante lenguaje natural.
- Confirmación explícita antes de crear o modificar registros; las acciones también pueden confirmarse o cancelarse con «sí» o «no».
- Selección guiada de archivos recientes de Descargas para adjuntarlos a ingresos o gastos existentes.
- Navegación entre secciones mediante instrucciones como «abre clientes» o «ve a mensualidades».
- Motor de interpretación determinista: no necesita LLM, Internet, GPU ni paquetes adicionales.
- Reconocimiento de voz opcional, bajo demanda, conectado al mismo agente.
- Puente opcional con NEXUS, aislado y desactivado por defecto.

## Actualizar desde versiones anteriores sin perder datos

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

## Novedades de 0.1.2

- Si se registra hoy un pago cuya fecha real fue anterior a otros pagos, la distribución de mensualidades se reconstruye por fecha de pago, luego fecha de registro e ID.
- Si se anula un pago que había cubierto cuotas antiguas, los pagos activos posteriores se vuelven a distribuir desde la cuota pendiente más antigua.
- Al consultar una fecha pasada, no se cuentan pagos cuya fecha de pago sea posterior a esa fecha.
- En Mensualidades se puede abrir el historial de pagos del cliente y comparar el importe original con lo aplicado a cuotas.
- Antes de guardar un voucher que ya existe, se muestra una advertencia con los movimientos coincidentes.

## Lógica de mensualidades

- El ciclo inicial comienza en la fecha de primer cobro registrada para el cliente.
- El día de cobro se repite cada mes y se ajusta al último día cuando el mes es más corto (por ejemplo, día 31 pasa a 30 o 28/29 cuando corresponde).
- Los ingresos solo afectan las mensualidades cuando se marca expresamente `Aplicar este ingreso a las mensualidades`.
- La distribución cubre primero los períodos abiertos más antiguos. Si sobra dinero, se generan períodos futuros y se asigna el saldo como abono.
- El importe original del movimiento nunca se cambia: se conserva el pago recibido y la distribución se almacena en otra tabla.
- La distribución se ordena por fecha real del pago. Registrar pagos fuera de orden o anular un pago provoca una reconstrucción para mantener cubiertas primero las cuotas más antiguas.
- Cambiar una tarifa no reescribe períodos que ya tengan abonos. Las cuotas futuras sin abonos pueden actualizarse a la nueva tarifa.
- Para anular un movimiento se exige un motivo. Sus distribuciones dejan de contar para los saldos.

## Agente financiero

En la sección «Agente» puedes escribir instrucciones para consultar y administrar el sistema. El motor actual es local y ligero; interpreta comandos sin cargar modelos de lenguaje.

Ejemplos:

- `Carlos me pagó 25 dólares por mensualidad mediante transferencia, voucher 2581`.
- `Pagué 18 dólares a Empresa Eléctrica por electricidad mediante efectivo`.
- `Crea un cliente Ana López con mensualidad de 23 dólares desde 2026-01-31`.
- `Cambia la mensualidad de Carlos a 30 dólares desde 2026-12-01`.
- `¿Cuánto debe Carlos?`, `Busca el voucher 2581`, `¿Cuál es el balance del mes?`.
- `Adjunta la descarga reciente al voucher 2581`.
- `Abre la sección de clientes`.

Los ingresos, gastos, clientes y cambios de tarifa se muestran primero como una vista previa. Debes confirmar la operación o cancelarla; el agente no guarda cambios financieros de manera silenciosa. Si hay varios comprobantes o movimientos posibles, te pide seleccionar el correcto.

## Agente por voz (opcional)

El agente escrito funciona sin reconocimiento de voz. Para habilitar la captura de una sola intervención por micrófono:

1. Instala los paquetes opcionales:

```powershell
.\.venv\Scripts\python.exe -m pip install -r installer\requirements_voice.txt
```

2. Descarga un modelo español compatible con Vosk y colócalo en `models/vosk-es/`.
3. Pulsa `Hablar` en la sección Agente.

No hay escucha permanente. El texto reconocido pasa por el mismo agente: puede consultar o preparar operaciones y seguirá requiriendo confirmación para guardar cambios.

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

## Alcance actual del agente

- La comprensión es basada en reglas y patrones; todavía no utiliza un modelo generativo local.
- Los nombres de clientes se deben pronunciar o escribir de forma suficientemente parecida al registro.
- La búsqueda de comprobantes revisa nombres y fechas de archivos recientes; no lee automáticamente el contenido del PDF o la imagen (OCR pendiente).
- Las operaciones pendientes viven en la sesión actual y se descartan si se cierra la aplicación antes de confirmar.

## Limitaciones de esta primera versión

- La interfaz está en una primera versión funcional y no incluye todavía edición directa de movimientos; se puede anular con motivo y registrar el movimiento corregido.
- No hay OCR automático de comprobantes ni lectura automática del contenido de transferencias de Descargas.
- El dictado de voz utiliza el agente y puede preparar registros; las operaciones siguen requiriendo confirmación.
- La conexión remota desde iPhone y el gestor inteligente de hardware se desarrollarán después de medir el consumo real.
- Los CSV se abren con Excel; la exportación XLSX/PDF se incorporará como módulo opcional.

## Seguridad

El programa guarda información financiera localmente. Protege la cuenta de Windows y el equipo con contraseña, conserva copias de seguridad cifradas fuera del dispositivo cuando sea posible y no compartas la carpeta de datos ni el token del puente.


## Novedades de 0.1.3

- Se reemplazaron las pestañas superiores por una barra lateral de navegación.
- Se añadió una transición horizontal breve al cambiar de sección.
- Los importes del panel principal cuentan suavemente hasta el valor actualizado.
- Se rediseñaron las tarjetas financieras, las acciones rápidas y la cabecera.
- Se agregaron atajos Ctrl+1 a Ctrl+7 para cambiar de sección.
- El tamaño inicial y mínimo se ajusta a la resolución disponible para evitar que la ventana salga de la pantalla.
- Las animaciones utilizan únicamente `after()` de Tkinter: no requieren GPU, procesos de fondo ni paquetes adicionales.
- Se conserva la base de datos y toda la lógica financiera de la versión 0.1.2.

## Novedades de 0.1.4

- Se eliminaron iconos y símbolos decorativos de la navegación, tarjetas y acciones rápidas.
- Se quitaron las etiquetas “local y privado”, “datos en este equipo”, “almacenamiento local” y mensajes similares de la interfaz.
- Se simplificó la cabecera, retirando la versión visible y los textos descriptivos redundantes.
- Se reorganizó el panel principal con tarjetas más limpias, mejor espaciado y acciones rápidas sin adornos.
- Se conservaron la navegación animada, el conteo de importes y todas las funciones financieras.

## Actualizaciones de código sin descargar ZIP cada vez

El proyecto incluye un actualizador incremental basado en Git. Se necesita Git for Windows una sola vez y un repositorio privado vacío de GitHub.

### Configuración inicial (solo una vez)

1. Instala Git for Windows: https://git-scm.com/download/win
2. Crea en GitHub un repositorio **privado y vacío**. No inicialices README, licencia ni `.gitignore`.
3. En la carpeta del proyecto ejecuta `configurar_actualizaciones.bat`.
4. Pega la URL HTTPS o SSH del repositorio. Git puede solicitar iniciar sesión mediante Git Credential Manager.
5. El asistente publicará el historial de código, sin incluir `data/`, evidencias, modelos, tokens ni copias de seguridad.

### Uso diario

- Abre el programa con `run_windows.bat` como siempre.
- Para recibir código nuevo, cierra el programa y ejecuta `actualizar.bat`.
- El actualizador descarga únicamente objetos/cambios nuevos del repositorio, aplica una actualización fast-forward, respalda `data/` antes de actualizar y vuelve a abrir el programa.
- Si no hay cambios, no descarga ni reemplaza el código.
- Si hay modificaciones locales sin guardar, se detiene para no sobrescribirlas.

**Importante:** para que una actualización llegue al computador, el nuevo código debe publicarse primero en el repositorio remoto. Hasta que el repositorio privado esté creado y vinculado, el actualizador queda preparado pero no puede recibir versiones nuevas. El ZIP de esta versión se usa únicamente para instalar una vez esta capacidad y configurar el remoto.
