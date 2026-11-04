# Estado del proyecto — Gestor Financiero

Este documento es la memoria técnica persistente del proyecto. Debe actualizarse en cada versión.

## Identidad y objetivo

Aplicación de escritorio financiera independiente, orientada primero a Windows y a equipos modestos. Está construida con Python, Tkinter y SQLite. No depende de NEXUS; el puente con NEXUS es opcional, separado y desactivado por defecto.

## Fuente de verdad

- La única línea principal de desarrollo es este repositorio Git.
- La rama principal contiene siempre la última versión completa y probada.
- Los ZIP de versiones anteriores son instantáneas históricas, no puntos de partida para nuevas funciones.
- Nunca reemplazar el proyecto completo desde una copia antigua para hacer una mejora visual.
- Antes de cada cambio, revisar el estado del repositorio y trabajar sobre el último código.

## Historial disponible

- `v0.1.0`: primera estructura funcional de pagos, clientes, mensualidades, evidencias y servicios financieros.
- `v0.1.1`: corrección de compatibilidad de esquema y migración aditiva para clientes existentes.
- `v0.1.2`: reconstrucción de asignaciones por fecha real de pago, anulaciones, consultas históricas y comprobación de vouchers repetidos.
- `v0.1.3`: navegación lateral y animaciones ligeras usando `after()` de Tkinter.
- `v0.1.4`: limpieza visual, retirada de iconos decorativos y textos redundantes.
- `v0.2.0`: agente financiero local con consultas, preparación de operaciones, confirmación, navegación y adjuntos de Descargas.
- `v0.3.0`: rediseño claro inspirado en panel financiero, gráficas interactivas con Canvas Tkinter y clasificación de gastos.
- `v0.4.0`: tres temas persistentes, diálogos/ventanas premium y selector de fecha desplegable en todos los campos de fecha de la interfaz.
- `v0.5.0`: calendario modal reconstruido como overlay dentro del formulario; exportación filtrada a PDF/XLSX/XML/TXT/CSV; estados de cuenta exportables; paquete completo de traslado `.gfbak` con hashes y restauración protegida; DPI nítido en Windows.
- `v0.6.0`: refinamiento de campos, botones, tablas y selectores; selector de temas movido al sidebar; selectores sin flecha lateral.
- `v0.6.1`: formularios con zona desplazable y pie fijo Guardar/Cancelar; cierre del calendario por clic exterior, botón o Escape; estilos de controles oscuros reforzados; acciones de exportar/evidencia no bloqueantes cuando no hay resultados; foco y cierre de ventanas premium reforzados.

La historia de Git contiene una instantánea de cada uno de esos paquetes.

## Arquitectura actual

- `main.py`: entrada de la aplicación.
- `src/database/`: conexión SQLite, esquema y migraciones.
- `src/domain/`: lógica de dinero y cálculo de mensualidades.
- `src/services/`: operaciones financieras, evidencias y reportes.
- `src/ui/`: ventana principal, vistas, diálogos premium, gestor de temas, calendario desplegable, gráficas Canvas interactivas y conversación con el agente.
- `src/agent/`: interpretación de instrucciones, consultas, borradores de operaciones y confirmación.
- `src/voice/`: reconocimiento de voz opcional que alimenta al agente.
- `src/integrations/`: puente opcional con NEXUS.
- `installer/`: empaquetado para Windows y requisitos opcionales.
- `tests/`: pruebas automatizadas.

## Funciones que no deben perderse

- Ingresos y gastos, con importe en centavos enteros.
- Clientes, identificación, tarifas con fecha de vigencia y día de cobro.
- Mensualidades, pagos parciales, adelantos y saldo a favor.
- El importe original del movimiento permanece intacto; las aplicaciones a cuotas se guardan aparte.
- Las asignaciones se reconstruyen por fecha real de pago, no por orden de captura.
- Anular un pago exige motivo y recalcula las cuotas afectadas.
- Las consultas a fecha histórica no usan pagos posteriores a esa fecha.
- Evidencias vinculadas a movimientos y almacenadas en la carpeta de datos.
- Búsqueda por persona, motivo, categoría, voucher y fechas; advertencia de voucher duplicado.
- Dashboard con balance acumulado registrado, ingresos/egresos del mes, evolución mensual de 12 meses, distribución de categorías y últimos movimientos.
- Gráfica de líneas: hover para ver los valores exactos, click en un mes para filtrar tabla y distribución, click en leyenda para ocultar/mostrar serie.
- Gráfica de anillo: click en una porción o categoría de leyenda para filtrar los movimientos del período.
- Categorías de gasto integradas en el registro. Las bases anteriores reciben la columna `category` con valor por defecto `Otros` mediante migración aditiva.
- Exportación de búsquedas y estados de cuenta a PDF, XLSX, XML, TXT y CSV; los formatos de datos completos preservan observaciones.
- Paquete portátil `.gfbak` con SQLite y evidencias verificadas por SHA-256, además de respaldo de reversión antes de restaurar.
- Interfaz sin iconos decorativos ni textos promocionales; animaciones discretas y ligeras.
- Temas Claro premium, Gris suave y Oscuro elegante, con preferencia persistente en `data/ui_preferences.json`.
- Diálogos de confirmación/aviso y ventanas secundarias con encabezado premium, cierre y animación breve.
- Calendarios desplegables en fecha de pago, inicio de cobro, vigencia de tarifa y filtros de búsqueda; el calendario es un overlay dentro de la ventana modal y no crea otro `Toplevel`. El formato interno continúa siendo ISO `AAAA-MM-DD`.
- Los diálogos de clientes, tarifas e ingresos/gastos usan cuerpo desplazable y acciones fijas en el pie, siempre accesibles dentro del área visible de la pantalla.
- Los diálogos premium cancelan sus tareas de animación al cerrarse, se elevan después de su creación y restauran la captura de foco de la ventana modal anterior.
- Dashboard, navegación y sondeo de voz cancelan sus tareas `after()` al destruir las vistas o cerrar la ventana principal.
- Las consultas UI a SQLite usan `get_connection()` para cerrar las conexiones al finalizar cada lectura.
- El calendario se cierra al pulsar nuevamente el botón, al hacer clic fuera o con Escape; mantiene intacta la captura modal del formulario.
- Los selectores nativos y controles de foco/casillas tienen colores específicos para el tema oscuro, evitando superficies claras residuales.
- En la búsqueda de movimientos, exportar sin resultados y abrir evidencia sin selección/evidencia muestran avisos no modales, sin abrir ventanas del sistema ni bloquear la interfaz.
- En Windows se declara DPI awareness por monitor; la ventana usa la resolución nativa disponible, sin limitar el programa a 720p.
- El puente NEXUS no es requisito para arrancar ni operar el programa.

## Invariantes financieros

1. Los valores monetarios se almacenan como enteros de centavos; no usar `float` para dinero.
2. Un gasto nunca debe generar asignaciones a mensualidades.
3. La suma aplicada a cuotas no puede superar el importe original de un ingreso.
4. Los pagos se aplican primero a las cuotas más antiguas elegibles.
5. Un cambio de tarifa no reescribe cuotas históricas ya abonadas.
6. Una anulación debe preservar el movimiento y su motivo de anulación; no borrar registros financieros.
7. Toda migración de base de datos debe ser aditiva, idempotente y respaldar la base antes de modificarla.

## Limitaciones conocidas de v0.6.1
- La interfaz, los calendarios y los diálogos se probaron con una sesión gráfica virtual (Xvfb); todavía falta validar la apariencia final en la computadora Windows del usuario con su resolución y escala DPI.
- El PDF es un resumen tabular de lectura: los textos largos se abrevian para conservar el ancho de página. Para conservar todas las observaciones y campos largos se debe usar XLSX, XML, TXT o CSV.
- El XML es un formato de intercambio de reportes, no una copia integral restaurable de la base de datos. Para trasladar todo el programa entre equipos se debe utilizar el paquete `.gfbak`, que incluye base y evidencias.

- No existe todavía edición directa de movimientos; el flujo actual es anular con motivo y volver a registrar.
- El agente puede preparar y confirmar registros por texto; el dictado por voz depende de instalar el módulo opcional de Vosk.
- La comprensión es actualmente determinista por reglas y patrones; todavía no utiliza un LLM local. La arquitectura permite añadir un motor conversacional opcional más adelante.
- El reconocimiento de voz es opcional y bajo demanda.
- No hay OCR automático de vouchers.
- Las gráficas se limitan a importes y categorías registradas; no infieren ni reconstruyen categorías antiguas, que migran a `Otros`.
- El gestor adaptativo de hardware y el instalador por perfiles están pendientes.
- La conexión desde iPhone/remota está pendiente.

## Siguiente trabajo recomendado

1. Probar la versión 0.6.1 en Windows real con los formularios de cliente, tarifa e ingreso/gasto, comprobando calendario, tema oscuro y acciones vacías sin bloquear la ventana.
2. Ampliar el lenguaje natural del agente y agregar memoria conversacional útil, sin comprometer la seguridad de los registros.
3. Terminar ficha de cliente y estado de cuenta con trazabilidad completa.
4. Agregar edición segura de movimientos mediante historial de cambios/auditoría, sin sobrescribir silenciosamente movimientos previos.
6. Medir consumo real y luego desarrollar el gestor de hardware.
7. Implementar OCR solo como módulo opcional y bajo demanda.

## Protocolo obligatorio para cada actualización

1. Leer este archivo, `CHANGELOG.md` y los tests antes de modificar código.
2. Cambiar la versión en `VERSION` y el registro en `CHANGELOG.md`.
3. No quitar funciones por hacer un rediseño visual; cambios estéticos deben limitarse a `src/ui/` salvo necesidad justificada.
4. Añadir pruebas de regresión para cada corrección funcional.
5. Ejecutar `python -m unittest discover -s tests -v` y pruebas de arranque/interfaz cuando sea posible.
6. Revisar `git diff` para detectar archivos eliminados o funciones perdidas accidentalmente.
7. Crear un commit con el cambio y generar el ZIP desde la rama principal actual.
8. No incluir bases de datos, comprobantes, tokens, logs ni copias de seguridad personales en los paquetes de distribución.
9. Nunca indicar que una prueba visual se hizo en Windows si solo se comprobó en otro entorno.

## Actualizaciones incrementales — v0.2.1 y posteriores

- Git es el mecanismo de sincronizacion del codigo, no de los datos personales.
- Configuracion unica: `configurar_actualizaciones.bat` enlaza el clon con un repositorio privado y publica la rama `main`.
- Actualizacion normal: cerrar la aplicacion y ejecutar `actualizar.bat`; `installer/update_windows.ps1` hace fetch, comprueba divergencias/cambios locales, respalda `data/` y aplica `git merge --ff-only`.
- Nunca subir `data/`, evidencias, tokens, modelos ni respaldos al remoto.
- El usuario configuró Git para Windows, vinculó el repositorio privado y confirmó el primer `git push -u origin master` desde su equipo. La rama remota activa es `master`.
- Las siguientes entregas deben aplicarse sobre este mismo historial, publicarse como commits en `origin/master` y recibirse mediante actualización incremental. No volver a entregar ZIP completos salvo para recuperación o instalación inicial.
- El conector de GitHub disponible en el entorno de desarrollo no tiene acceso confirmado al repositorio privado; cuando no exista ese acceso, entregar un parche Git verificable para que el usuario lo aplique y publique.
- Pendiente: integrar la comprobación/aplicación de actualizaciones dentro de la aplicación y eliminar la consola visible del flujo normal de actualización. El acceso directo de uso diario debe arrancar con `pythonw.exe` o el ejecutable empaquetado, nunca con una consola.


## Estado visual v0.6.0–v0.6.1
- Los controles `ttk` usan estilos de campos y botones refinados y coherentes con el tema activo.
- Todos los selectores de la interfaz se implementan mediante `src.ui.widgets.ElegantCombobox`, que elimina visualmente la flecha lateral y abre el popdown al hacer clic en toda la barra.
- El selector de temas vive en la parte inferior del sidebar, abre un panel flotante y actualiza el tema sin un `Combobox` editable/seleccionable.
- El menú de Datos usa un panel de acciones sin flecha lateral.
- Los formularios extensos usan un canvas desplazable y un footer fijo para que Guardar/Cancelar no queden fuera de pantalla.
- Los calendarios globales se gestionan por raíz Tk mediante un dispatcher ligero; se cierran por clic exterior, Escape o el botón de calendario y se retiran de la lista activa al cerrar/destruir.
- El tema oscuro configura la lista desplegable nativa de `ttk.Combobox`, los indicadores de casillas, colores de foco, bordes de Treeview y scrollbars.
- Las acciones de movimientos sin selección o sin resultados responden con un mensaje inline temporizado y no abren modales innecesarios.
- No cambiar la persistencia de `data/ui_preferences.json` ni el motor financiero al continuar refinando la UI.
