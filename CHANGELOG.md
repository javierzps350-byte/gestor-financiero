# Historial de cambios

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
