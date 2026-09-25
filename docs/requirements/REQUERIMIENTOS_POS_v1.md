# Requerimientos · LI Punto de Venta

**Versión:** 1.1 · **Fecha:** 24 de septiembre de 2026 · **Estado:** borrador para validación funcional

## 1. Objetivo y alcance

Construir un punto de venta preparado inicialmente para seis sucursales, con configuración de razones sociales, con ventas, caja, productos, inventario, clientes, compras, facturación y reportes. Tomamos como referencia los módulos discutidos para TPN/Sicar X y la estructura ya creada en LI-PUNTO-DE-VENTA. La implementación actual es una demostración y no procesa operaciones productivas.

**Flujo principal:** iniciar sesión → seleccionar sucursal y caja autorizadas → abrir caja → buscar o escanear productos → armar carrito → validar existencias y precios → confirmar cobro → registrar venta, movimiento de inventario y auditoría → entregar comprobante → realizar corte de caja.

## 2. Actores y permisos

| Rol | Funciones esperadas | Alcance |
|---|---|---|
| Administrador general | Configuración, empresas, sucursales, usuarios, precios, reportes globales | Empresas y sucursales autorizadas |
| Administrador de sucursal | Catálogo local, caja, ventas, inventario, reportes locales | Su sucursal |
| Vendedor / Cajero | Abrir y cerrar su caja, vender, consultar productos, emitir comprobante | Caja y sucursal asignadas |
| Almacenista | Recepciones, conteos y movimientos de inventario | Almacenes asignados |
| Supervisor de inventarios | Aprobar ajustes y traspasos, revisar diferencias | Sucursales asignadas |
| Contabilidad | Consultar ventas, impuestos y facturas, conciliar | Empresas autorizadas |
| Repartidor | Consultar entregas asignadas y registrar estado | Órdenes asignadas |
| Auditoría / Consulta | Consultas y bitácora en modo lectura | Ámbito autorizado |

**Regla obligatoria:** el servidor obtiene la empresa de la identidad autenticada; valida también cada sucursal, caja y permiso antes de leer o cambiar datos. Ningún usuario se otorga permisos por enviar IDs en el cuerpo de una petición.

## 3. Requerimientos funcionales

| ID | Módulo | Requerimiento verificable | Prioridad |
|---|---|---|---|
| RF-01 | Identidad | Inicio/cierre de sesión, recuperación segura, permisos por rol y sucursal; bloqueo de acceso no autorizado | P0 |
| RF-02 | Configuración | Registrar razones sociales, sucursales, cajas, impuestos, series/folios y parámetros operativos | P0 |
| RF-03 | Catálogo | Crear/editar productos con SKU o código de barras único por empresa, nombre, unidad, precio, impuesto y estado | P0 |
| RF-04 | Inventario | Consultar stock por sucursal; registrar entradas, salidas, ajustes y kardex sin sobrescribir historial | P0 |
| RF-05 | POS | Buscar por nombre/SKU y leer código con escáner; carrito con cantidades, descuentos autorizados y totales visibles | P0 |
| RF-06 | Venta | Antes de confirmar, comprobar permisos, caja abierta, existencia, precios e importe; guardar venta y descuento de stock en una transacción | P0 |
| RF-07 | Cobro | Registrar efectivo, tarjeta y transferencia; validar recibido y cambio; integrar terminal Clip solo tras conciliación y credenciales aprobadas | P0 |
| RF-08 | Caja | Apertura, retiros autorizados, entradas, arqueo, corte, diferencias y cierre con responsable y hora | P0 |
| RF-09 | Comprobantes | Folio único por empresa/sucursal, ticket térmico 80 mm y comprobante carta con desglose de impuestos | P1 |
| RF-10 | Clientes | Alta, búsqueda e historial de compras; datos fiscales separados y acceso restringido | P1 |
| RF-11 | Compras | Proveedores, órdenes, recepciones parciales y actualización trazable de existencias | P1 |
| RF-12 | Devoluciones | Referenciar venta original, validar cantidades y autorización; reintegro y retorno a inventario según estado del producto | P1 |
| RF-13 | Traspasos | Solicitud, salida, recepción y conciliación entre sucursales con estados auditables | P1 |
| RF-14 | Facturación | Preparar CFDI y timbrar mediante PAC seleccionado; guardar UUID, XML, PDF y cancelaciones autorizadas | P1 |
| RF-15 | Reportes | Ventas, formas de pago, cortes, existencias, movimientos, márgenes y desempeño por sucursal/periodo | P1 |
| RF-16 | Auditoría | Bitácora inmutable de ventas, cancelaciones, devoluciones, precios, inventario, caja, permisos y accesos | P0 |
| RF-17 | Comunicación | Ofrecer enlace de WhatsApp para compartir comprobante tras venta, sin enviarlo automáticamente | P2 |
| RF-18 | Offline | Permitir continuidad controlada de caja sin internet, sincronizar sin duplicar ventas y conciliar conflictos | P1, diseño antes de producción |
| RF-19 | Cotizaciones / multiservicios | Preparar cotizaciones y servicios adicionales según catálogo aprobado | P2 |

**Prioridades:** P0 = indispensable para operación segura; P1 = siguiente fase; P2 = extensión posterior. P0 no implica que ya esté implementado.

## 4. Reglas de negocio

1. LI operará inicialmente con seis sucursales configurables: Zamora, Zacapu, Uruapan, 20 de Noviembre, Maravatío y CDMX, conforme al escenario de TPN. Las sucursales se administran como registros; no se codifican como constantes. Se mantiene por confirmar cuántas razones sociales usará LI y la asignación fiscal de cada sucursal.
2. Cada producto y venta pertenece a una empresa; el stock, la caja y la venta también pertenecen a una sucursal autorizada. El folio debe ser único dentro de su serie.
3. Los precios, descuentos e impuestos se calculan y validan en el servidor. El 16 % fijo y los precios antes de IVA de la demo son supuestos temporales; el tratamiento fiscal real será configurable por producto y operación.
4. No se puede vender una cantidad superior al stock disponible, salvo una política explícita de venta bajo pedido aprobada posteriormente.
5. Una venta confirmada no se borra: se cancela o devuelve mediante eventos nuevos con motivo, autorización y trazabilidad. La bitácora y el kardex son de solo adición.
6. Cada intento de cobro lleva una clave de idempotencia para evitar duplicados, especialmente ante fallos de red o reintentos de sincronización.
7. Un retiro requiere caja abierta, importe positivo, motivo, usuario y permiso; el corte muestra efectivo esperado, contado y diferencia.
8. El pago con terminal no se considera exitoso hasta confirmar el resultado con el proveedor; el registro manual se distingue claramente del cobro electrónico confirmado.
9. La factura requiere datos fiscales validados, relación con la venta y respuesta comprobable del PAC. No se inventan UUID ni estados de timbrado.

## 5. Requerimientos no funcionales

| ID | Condición | Criterio de aceptación |
|---|---|---|
| RNF-01 | Seguridad | Contraseñas con hash robusto, sesiones con expiración, permisos verificados en API, secretos fuera del repositorio |
| RNF-02 | Aislamiento | Pruebas que demuestren que empresa/sucursal no ven ni modifican registros ajenos |
| RNF-03 | Integridad | Venta, partidas, existencias y auditoría se confirman o revierten juntos; concurrencia sin sobreventa |
| RNF-04 | Disponibilidad | Respaldo y restauración probada; modo offline con cola duradera antes de uso en tienda |
| RNF-05 | Usabilidad | Interfaz en español, adaptable a caja y tableta, búsqueda rápida y navegación sin recarga |
| RNF-06 | Observabilidad | Errores y eventos trazables por folio/ID sin exponer credenciales o datos sensibles |
| RNF-07 | Datos | PostgreSQL como base de producción; migraciones versionadas y cambios reversibles cuando proceda |
| RNF-08 | Rendimiento | Objetivos medibles en piloto: búsqueda local < 1 s y confirmación de venta en línea < 3 s en condiciones normales; validar en hardware real |

## 6. Estado frente al código actual

| Área | Estado al crear este documento |
|---|---|
| Catálogo, existencias, carrito, cobro registrado, historial básico, auditoría de venta | Demo funcional |
| Aislamiento por empresa | Prueba básica con cabecera de demostración; sin autenticación real |
| Sucursal/caja autorizadas, roles, impuestos configurables, folios, kardex, cortes | Pendiente |
| Clip, CFDI/PAC, WhatsApp, devoluciones, compras, reportes y offline | Pendiente |
| Bloqueo de producción | Activo: `APP_ENV=production` rechaza operaciones hasta implementar autenticación |

## 7. Entrega por fases y aceptación

- **Fase 0 — definición:** confirmar sucursales, empresas, impuestos, reglas de descuentos, flujo de caja, proveedor PAC y pagos. Aprobar prototipo de ticket y matriz de permisos.
- **Fase 1 — núcleo operable:** identidad/RBAC, empresa/sucursal, catálogo, inventario con kardex, caja, venta, folio y ticket; pruebas de concurrencia, aislamiento y cierre de caja. **Aceptación:** venta completa de apertura a corte, sin mezcla de datos ni sobreventa.
- **Fase 2 — operación ampliada:** clientes, compras, devoluciones, traspasos, reportes y auditoría avanzada. **Aceptación:** conciliación de cantidades y dinero por sucursal.
- **Fase 3 — integraciones:** PAC/CFDI, Clip y enlace WhatsApp. **Aceptación:** pruebas con proveedor y evidencia de conciliación/errores.
- **Fase 4 — resiliencia y despliegue:** caja offline, reintentos idempotentes, respaldos, monitoreo y piloto. **Aceptación:** simular caída de red, recuperación, restauración y conciliación sin ventas duplicadas.

## 8. Definiciones pendientes

1. Confirmar el nombre oficial y los datos de cada una de las seis sucursales, así como el número de razones sociales de LI y la asignación fiscal de cada sucursal.
2. Definir si los precios incluyen IVA, productos exentos/tasa cero, descuentos, promociones y política de venta a crédito.
3. Elegir PAC y aclarar si Clip será cobro integrado, registro manual inicial o ambos; confirmar modelo de terminal y certificaciones necesarias.
4. Especificar impresoras, lectores, cajones, equipos Windows, funcionamiento offline y volumen esperado por sucursal.
5. Acordar política de devoluciones, cancelaciones, retiros, autorización y conservación de comprobantes.

Estas decisiones no impiden comenzar el diseño del núcleo, pero sí condicionan el uso productivo.
