# Devoluciones de ventas

En Productos y ventas, abre Devoluciones junto al ticket en Últimas ventas. Administrador general y administrador de sucursal pueden registrar devoluciones en sus sucursales autorizadas. Cajeros y consulta pueden consultar el historial.

Selecciona cantidades pendientes, motivo y si cada partida se reintegra al inventario. La mercancía dañada puede devolverse sin aumentar existencias. El importe usa el precio, descuento e impuestos guardados en el ticket, con redondeo acumulado para conservar todos los centavos en devoluciones parciales.

Para efectivo selecciona un turno abierto de la misma sucursal con saldo suficiente. El reembolso se registra como movimiento refund en ese turno; no modifica el corte del turno original cerrado. Tarjeta y transferencia requieren realizar el reembolso fuera de la aplicación e introducir su referencia. No se envía dinero al proveedor ni se cancela un CFDI.

La operación conserva ticket original, partidas, responsable, motivo, comprobante interno, movimientos de stock y auditoría. Los reportes de resumen muestran total neto, total bruto y devoluciones. Las claves de reintento evitan duplicados y se impide devolver más de lo vendido.

## Actualizar Windows

Detén el servidor usando el identificador de proceso que mostró el inicio. Ejecuta git pull y después INICIAR_LI_POS.bat. El iniciador ejecuta scripts/migrate_local.py con respaldo de pos.db antes de actualizar. No borres pos.db. Recarga el navegador con Ctrl+F5 e inicia sesión otra vez.

Las ventas antiguas sin desglose usan asignación proporcional del total histórico. Las ventas antiguas con descuentos sin desglose requieren revisión y no permiten devolución automática. Cancelaciones y CFDI siguen pendientes.

## Validación

python -m pytest tests/test_returns.py tests/test_operations.py tests/test_sales.py tests/test_operations_migration.py -q

Pruebas de integración SQLite: parciales y totales, redondeo e impuestos/descuentos, reintentos, permisos y empresa/sucursal, efectivo insuficiente o turno cerrado, no reintegro, reembolso externo, atomicidad, concurrencia y migración conservando datos. La interfaz requiere prueba en navegador y PostgreSQL requiere validación antes de producción.
