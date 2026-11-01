# Agente financiero local

## Responsabilidad

El agente traduce instrucciones del usuario a consultas o borradores de operaciones del Gestor Financiero. No accede directamente a la base de datos: utiliza funciones de `src.services` para respetar validaciones, asignaciones mensuales y auditoría.

## Diseño ligero

- No usa servicios de IA externos.
- No carga un LLM local en la instalación base.
- No requiere GPU ni paquetes Python adicionales.
- La interfaz puede enviar texto reconocido por Vosk al mismo controlador.
- La lógica de interpretación está separada de Tkinter para poder probarla y evolucionarla.

## Operaciones

- Consultar ingresos, gastos, balance mensual, lista de clientes, deudores, saldos y vouchers.
- Buscar movimientos por texto.
- Navegar entre secciones de la aplicación.
- Preparar ingresos y gastos.
- Crear clientes y cambiar tarifas.
- Encontrar archivos recientes de Descargas y adjuntarlos a movimientos existentes.

## Seguridad de las operaciones

Las operaciones de escritura se conservan como `pending` dentro de la sesión. El usuario debe revisar los datos y confirmar mediante el botón o una respuesta afirmativa. Una respuesta negativa cancela el borrador. Cuando falta un campo obligatorio, el agente solicita el dato y bloquea la confirmación. Las asociaciones de evidencias ambiguas requieren seleccionar el movimiento y el archivo.

No se permite borrar movimientos mediante el agente. La anulación requiere el flujo existente del programa y un motivo obligatorio.

## Extensión futura

Se puede añadir un motor opcional de lenguaje natural detrás del mismo controlador. Este motor deberá devolver intenciones y campos estructurados; nunca tendrá permiso de ejecutar SQL ni escribir en SQLite por su cuenta. La confirmación y las validaciones de los servicios seguirán siendo obligatorias.
