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

La historia de Git contiene una instantánea de cada uno de esos paquetes.

## Arquitectura actual

- `main.py`: entrada de la aplicación.
- `src/database/`: conexión SQLite, esquema y migraciones.
- `src/domain/`: lógica de dinero y cálculo de mensualidades.
- `src/services/`: operaciones financieras, evidencias y reportes.
- `src/ui/`: ventana principal, vistas, diálogos y asistente.
- `src/voice/`: reconocimiento de voz opcional.
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
- Búsqueda por persona, motivo, voucher y fechas; advertencia de voucher duplicado.
- Exportación CSV y copias de seguridad.
- Interfaz sin iconos decorativos ni textos promocionales; animaciones discretas y ligeras.
- El puente NEXUS no es requisito para arrancar ni operar el programa.

## Invariantes financieros

1. Los valores monetarios se almacenan como enteros de centavos; no usar `float` para dinero.
2. Un gasto nunca debe generar asignaciones a mensualidades.
3. La suma aplicada a cuotas no puede superar el importe original de un ingreso.
4. Los pagos se aplican primero a las cuotas más antiguas elegibles.
5. Un cambio de tarifa no reescribe cuotas históricas ya abonadas.
6. Una anulación debe preservar el movimiento y su motivo de anulación; no borrar registros financieros.
7. Toda migración de base de datos debe ser aditiva, idempotente y respaldar la base antes de modificarla.

## Limitaciones conocidas de v0.1.4

- No existe todavía edición directa de movimientos; el flujo actual es anular con motivo y volver a registrar.
- El asistente puede consultar; no registra pagos dictados.
- El reconocimiento de voz es opcional y bajo demanda.
- No hay OCR automático de vouchers.
- La exportación XLSX/PDF aún no está terminada; existe CSV.
- El gestor adaptativo de hardware y el instalador por perfiles están pendientes.
- La conexión desde iPhone/remota está pendiente.

## Siguiente trabajo recomendado

1. Probar la versión con la base de datos real del usuario y corregir incidencias sin tocar ni borrar sus datos.
2. Terminar ficha de cliente y estado de cuenta con trazabilidad completa.
3. Agregar edición segura de movimientos mediante historial de cambios/auditoría, sin sobrescribir silenciosamente movimientos previos.
4. Incorporar exportación PDF/XLSX como dependencias opcionales.
5. Medir consumo real y luego desarrollar el gestor de hardware.
6. Implementar captura por voz y OCR solo como módulos opcionales.

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
