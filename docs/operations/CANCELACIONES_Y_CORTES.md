# Cancelaciones y cortes de caja

## Cancelar una venta

En Últimas ventas, administración puede seleccionar Cancelar venta. Se confirma el motivo, importe completo y turno que entrega efectivo o referencia de reembolso externo. La cancelación devuelve todas las unidades al inventario y conserva el ticket original con estado Cancelada, responsable, auditoría y comprobante. No elimina ventas ni cancela CFDI ni envía dinero a una terminal.

Una venta con devoluciones anteriores no se puede cancelar: se completa la devolución de las cantidades pendientes. Una venta cancelada bloquea devoluciones nuevas y otra cancelación. Los reintentos de la misma operación no duplican inventario ni reembolso. Se aplica el precio, descuento e impuestos históricos.

## Corte

Cajas y turnos → Historial de turnos → Ver corte muestra un corte provisional si el turno está abierto. Incluye ventas e importes por efectivo, tarjeta y transferencia, reembolsos de tickets del turno, fondo, entradas, retiros, reembolsos efectivamente entregados por el turno, esperado, contado y diferencia. Se puede imprimir desde el comprobante.

El efectivo esperado usa fondo + ventas en efectivo + entradas - retiros - reembolsos entregados. Tarjeta y transferencia son registros manuales y no aumentan el efectivo esperado. Los reembolsos de tickets y el efectivo entregado son perspectivas diferentes, no cantidades que deban sumarse entre sí.

Al cerrar se guarda un snapshot del desglose, fecha y usuario del cierre. Una devolución posterior se paga desde un turno abierto; no cambia el corte anterior. Los cortes anteriores a esta actualización conservan su esperado original si existe, pero no poseen snapshot histórico del desglose; el comprobante lo indica.

## Actualizar

Detén el servidor, ejecuta git pull y después INICIAR_LI_POS.bat. El iniciador respalda pos.db y ejecuta la migración. Recarga con Ctrl+F5 y vuelve a iniciar sesión para obtener los permisos nuevos. No borres la base.

## Pruebas

python -m pytest tests/test_cancel_cut.py tests/test_returns.py tests/test_operations.py tests/test_sales.py tests/test_operations_migration.py -q

Validación SQLite: cancelación completa, reintentos, permisos/empresa, bloqueo de devoluciones previas, concurrencia, caja insuficiente, reembolso externo, pagos mixtos, cierre con diferencia, snapshot estable ante cancelación posterior y migraciones. Falta validar visualmente en navegador y ejecutar las pruebas en PostgreSQL antes de producción.
