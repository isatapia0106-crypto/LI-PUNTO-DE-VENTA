# Reversos y devoluciones a proveedor

## Reverso de abono

Administración y contabilidad pueden revertir un abono manual con motivo. No se borra: conserva importe, referencia, actor y fecha originales, añade responsable/fecha/motivo del reverso y evento de auditoría. El cálculo excluye abonos revertidos y recalcula saldo, vencimiento y crédito a favor. No devuelve dinero ni altera caja. Un reverso repetido con igual motivo devuelve el original; otro motivo da conflicto. Reintentar el abono original con su clave no lo reactiva.

## Devolución física con crédito aceptado

Administración puede registrar cantidades de una compra completamente recibida y con cuenta por pagar reconocida. Debe capturar motivo y referencia del crédito aceptado por proveedor. Una transacción descuenta existencias y registra crédito contra la cuenta, conservando recepciones, partidas originales e historial. No crea CFDI ni llama a un banco. Sólo representa el acuerdo documentado con el proveedor por el importe calculado.

Límites: cantidad acumulada devuelta no excede lo recibido; sólo productos de esa compra; existencias actuales suficientes y libres de reservas. Los permisos de compras, inventario y cuentas por pagar se exigen en servidor, además de empresa/sucursal. Bloqueos comunes de sucursal serializan ventas, abonos, reversos y devoluciones. Clave idempotente evita duplicar reintentos; no reuse una clave con otra cantidad o motivo.

Crédito por partida: total original con impuestos distribuido proporcionalmente por cantidad mediante redondeo acumulado. La última devolución conserva los centavos originales. Se usa precio/impuesto histórico de la compra; no el catálogo actual. Inventario se reduce manteniendo el costo promedio actual de las unidades restantes; no se reconstruye valoración por lotes ni contabilidad fiscal.

Saldo = importe original - abonos vigentes - créditos de devolución. Si es negativo, muestra saldo pendiente cero y «A favor» por el excedente; no supone dinero recibido del proveedor. Todavía no se consume ese crédito en otras facturas ni se registra su cobro bancario.

Interfaz: en cuentas, botón «Revertir abono» y detalle histórico; en órdenes recibidas, «Devolver a proveedor» e historial. Requiere evidencia externa y captura de referencia del crédito. No permite devolver compras parciales/canceladas, anticipos ni créditos por importes distintos de lo calculado. No hay reversión de devolución física en esta entrega. Revisar datos antes de confirmar.

Migración 6f39ac4167b8 añade campos nulos de reverso y tabla vacía de devoluciones. Los abonos anteriores permanecen vigentes. Ejecutar scripts/migrate_local.py con servidor detenido; se conserva respaldo. Pruebas cubren permisos, duplicados, saldo, concurrencia, reservas y centavos; piloto real pendiente.
