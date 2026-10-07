# Impuestos de compra

En una nueva orden, cada partida permite capturar costo unitario sin impuestos y tasa porcentual (0 a 100 %, precisión de dos decimales de porcentaje). La API recibe tax_rate como proporción (0.16 = 16 %) y guarda la tasa en la partida histórica. No obtiene la tasa del producto vendido ni modifica la orden al editar el catálogo.

Redondeo: subtotal de partida = costo unitario × cantidad, redondeado a centavos; impuesto = subtotal de partida × tasa, redondeado a centavos. El subtotal y el impuesto de la orden suman las partidas redondeadas. Total = subtotal + impuesto. El campo total_cost sigue representando subtotal sin impuestos. Esta regla se aplica en la lectura de órdenes; órdenes antiguas con costos fraccionarios pueden mostrar diferencias de centavos frente al antiguo redondeo global.

Una recepción parcial actualiza existencias y costo promedio con el costo unitario sin impuestos. No genera una factura fiscal, un pago a proveedor ni impuesto acreditable. La cancelación de pendientes conserva tasas y el valor original de la orden; el total de la orden no representa una cuenta por pagar vigente.

Tasa cero no distingue exento/no objeto/tasa cero fiscalmente. La captura requiere validación del negocio; no sustituye el CFDI del proveedor. Retenciones, múltiples impuestos por partida, tratamiento de IVA no acreditable y cuentas por pagar quedan pendientes.

Migración 4d178a2f4596: partidas antiguas reciben tasa cero; conserva costos, cantidades y recepciones. No supone 16 % para operaciones pasadas. Ejecutar scripts/migrate_local.py con servidor detenido antes de iniciar la versión actualizada.
