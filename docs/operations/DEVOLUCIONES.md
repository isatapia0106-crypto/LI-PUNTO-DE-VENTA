# Devoluciones de ventas

En Productos y ventas, abre Devoluciones junto al ticket en Últimas ventas. Administrador general y administrador de sucursal pueden registrar devoluciones en sus sucursales autorizadas. Cajeros y consulta pueden consultar el historial.

Selecciona cantidades pendientes, motivo y si cada partida se reintegra al inventario. La mercancía dañada puede devolverse sin aumentar existencias. El importe usa el precio, descuento e impuestos guardados en el ticket, con redondeo acumulado para conservar todos los centavos en devoluciones parciales.

Para efectivo selecciona un turno abierto de la misma sucursal con saldo suficiente. El reembolso se registra como movimiento refund en ese turno; no modifica el corte del turno original cerrado. Tarjeta y transferencia requieren realizar el reembolso fuera de la aplicación e introducir su referencia. Estas formas manuales no envían dinero al proveedor. Para Mercado Pago se usa el flujo integrado descrito abajo. No se cancela un CFDI.

La operación conserva ticket original, partidas, responsable, motivo, comprobante interno, movimientos de stock y auditoría. Los reportes de resumen muestran total neto, total bruto y devoluciones. Las claves de reintento evitan duplicados y se impide devolver más de lo vendido.

## Actualizar Windows

Detén el servidor usando el identificador de proceso que mostró el inicio. Ejecuta git pull y después INICIAR_LI_POS.bat. El iniciador ejecuta scripts/migrate_local.py con respaldo de pos.db antes de actualizar. No borres pos.db. Recarga el navegador con Ctrl+F5 e inicia sesión otra vez.

Las ventas antiguas sin desglose usan asignación proporcional del total histórico. Las ventas antiguas con descuentos sin desglose requieren revisión y no permiten devolución automática. La cancelación completa está disponible; la cancelación de CFDI requiere integración fiscal.

## Validación

python -m pytest tests/test_returns.py tests/test_operations.py tests/test_sales.py tests/test_operations_migration.py -q

Pruebas de integración SQLite: parciales y totales, redondeo e impuestos/descuentos, reintentos, permisos y empresa/sucursal, efectivo insuficiente o turno cerrado, no reintegro, reembolso externo, atomicidad, concurrencia y migración conservando datos. Las pruebas automatizadas con PostgreSQL y restauración de respaldo están disponibles en GitHub Actions. Faltan aceptación visual y transacciones controladas con el proveedor real.

## Devolución integrada de Mercado Pago

Selecciona las cantidades, si se reintegran y el motivo. El sistema calcula el
reembolso desde el ticket y solicita esa cantidad a Mercado Pago, sin referencia
manual ni movimiento de efectivo. Admite parciales y cancelación completa. Guarda
la solicitud, partidas, importe, saldo reembolsado anterior y UUID antes de llamar
al proveedor. Hay una sola operación pendiente por ticket: no se permite otra hasta
confirmarla. Las cantidades pendientes no se muestran como ya devueltas ni se
reintegran físicamente, y no afectan los reportes o el estado Cancelada del ticket.

Un POST exitoso no basta. El servidor vuelve a consultar el pago y exige el importe
acumulado esperado, cuenta, empresa, moneda y entorno. Sólo entonces confirma la
devolución, movimientos de inventario y auditoría en una transacción. Los reportes
usan la fecha de confirmación; la fecha original de solicitud se conserva. El corte
cerrado queda idéntico. La mercancía no reintegrable conserva su costo como pérdida.

Si se pierde la respuesta o el saldo aún no coincide, abre Devoluciones junto al
mismo ticket y pulsa **Consultar y reintentar reembolso** en su historial. Se utiliza
el mismo UUID e importe, no otro cobro ni otra devolución. Si el pago ya muestra el
acumulado esperado, se confirma localmente sin enviar un segundo reembolso. En ese
caso puede faltar el ID del reembolso; la referencia indica verificación por saldo.
Una discrepancia con reembolsos externos o un contracargo queda pendiente para
conciliación: no se adivinan importes ni se borran solicitudes financieras.

Las devoluciones antiguas se conservan como confirmadas. Los reembolsos parciales
pueden ser rechazados por el proveedor según el medio de pago; la operación queda
pendiente y exige revisión. No hay borrado o abandono automático de una devolución
pendiente. Las pruebas de Mercado Pago usan respuestas simuladas; valida el flujo
con cuentas de prueba antes de habilitar cobros o reembolsos reales.
