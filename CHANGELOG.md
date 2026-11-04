# Historial de cambios

## [0.4.0] — Temas, calendarios y ventanas premium
- Se incorporaron tres temas seleccionables y persistentes: Claro premium, Gris suave y Oscuro elegante.
- El cambio de tema actualiza tarjetas, paneles, tablas, gráficas, navegación, asistente, formularios y colores de estado; la preferencia se guarda en `data/ui_preferences.json`.
- Se añadieron ventanas emergentes de estilo premium para avisos, confirmaciones, selección de evidencias, historial de pagos y anulación de movimientos.
- Las ventanas secundarias incorporan encabezado propio, acento de color, cierre, movimiento por arrastre y entrada con fundido suave.
- Se añadió un calendario desplegable en primera fecha de cobro, fecha de vigencia de tarifa, fecha de pago y filtros Desde/Hasta. El valor continúa guardándose como `AAAA-MM-DD` y también puede escribirse manualmente.
- El calendario se posiciona para permanecer dentro de la pantalla y permite cambiar de mes o seleccionar rápidamente la fecha de hoy.
- No se añadieron dependencias externas; se mantiene Tkinter/Canvas para conservar el rendimiento en equipos modestos.
- Se corrigió la adaptación de colores de widgets Tk clásicos para evitar colores de texto de bajo contraste al alternar temas.
- Se añadieron pruebas para las paletas, persistencia de tema y matriz del calendario.

## [0.3.0] — Panel financiero interactivo
- Rediseño general del programa con una interfaz clara, tarjetas blancas y navegación lateral compacta.
- Nuevo panel con saldo acumulado registrado, ingresos del mes y egresos del mes.
- Gráfica de evolución de ingresos y gastos de los últimos 12 meses, con tooltips al pasar el cursor, selección de mes y leyenda para activar/desactivar series.
- Gráfica de anillo por categoría de gasto; permite seleccionar segmentos o categorías de la leyenda para filtrar los movimientos.
- Tabla de últimos movimientos con fecha, descripción, categoría, tipo de pago e importe.
- Se incorporó la categoría de gasto al registro de egresos. Los movimientos antiguos se migran como “Otros” sin perder datos.
- Búsquedas y exportaciones CSV incluyen la categoría.
- Las gráficas se dibujan con Canvas de Tkinter: no requieren GPU, Matplotlib ni dependencias externas.
- Se añadieron pruebas para agregaciones del panel y migración de bases antiguas.

## 0.2.1 — Actualizaciones incrementales

- Se añadieron `actualizar.bat` y `installer/update_windows.ps1` para recibir cambios mediante Git sin descargar un ZIP completo en cada versión.
- Se añadió `configurar_actualizaciones.bat` para vincular una sola vez la instalación con un repositorio privado.
- El actualizador comprueba cambios locales antes de actuar y se niega a sobrescribir código modificado.
- Antes de aplicar una actualización crea un respaldo ZIP de `data/` en `%LOCALAPPDATA%\GestorFinanciero\update_backups`.
- Las actualizaciones se aplican con fast-forward; no fuerzan ni descartan cambios locales.
- La base de datos, evidencias y copias de seguridad permanecen fuera del historial Git mediante `.gitignore`.

## [0.2.0]
- Se incorporó un agente financiero local, independiente de NEXUS y sin modelos pesados.
- El agente consulta ingresos, gastos, balance mensual, clientes, deudas y vouchers.
- Puede preparar ingresos, gastos, clientes y cambios de tarifa mediante instrucciones en lenguaje natural.
- Las operaciones que modifican datos requieren revisión y confirmación explícita; se puede confirmar o cancelar con botones o por texto/voz.
- Puede localizar descargas recientes y asociarlas a ingresos o gastos después de seleccionar el movimiento y el archivo correctos.
- Puede navegar entre las secciones del programa mediante instrucciones.
- Se añadió una interfaz conversacional y una capa separada `src/agent/`.
- El reconocimiento de voz sigue siendo opcional y bajo demanda; el motor principal no requiere Internet, GPU ni paquetes externos.

## [0.1.4]
- Interfaz depurada: se quitaron iconos decorativos y textos redundantes.
- Se simplificaron cabecera, tarjetas y acciones rápidas.
- Se conservaron navegación y animaciones ligeras.

## [0.1.3]
- Navegación lateral.
- Transiciones breves entre secciones y animación de importes.
- Atajos Ctrl+1 a Ctrl+7.
- Ajuste del tamaño inicial a la pantalla.

## [0.1.2]
- Reasignación de pagos fuera de orden según fecha real.
- Reapertura y redistribución de cuotas al anular pagos.
- Consultas históricas excluyen pagos posteriores.
- Historial de pagos y aviso de vouchers duplicados.

## [0.1.1]
- Migraciones aditivas para bases SQLite existentes.
- Corrección de campos de cliente faltantes y respaldo previo a migrar.

## [0.1.0]
- Primera versión del registro financiero, clientes, mensualidades, evidencias, búsqueda y puente opcional.

## Regla de mantenimiento

Cada cambio futuro debe agregarse arriba de este registro. No se deben borrar entradas de versiones anteriores.
