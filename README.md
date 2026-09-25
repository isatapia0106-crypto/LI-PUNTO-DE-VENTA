# LI Punto de Venta

Estructura inicial para desarrollar un sistema de punto de venta, basada en los módulos conocidos del proyecto TPN.

## Orden de carpetas

1. `backend/`: API, lógica de negocio, integraciones, migraciones y pruebas.
2. `frontend/`: interfaz de caja y administración.
3. `desktop/`: empaquetado y acceso a hardware local.
4. `database/`: migraciones y datos de ejemplo.
5. `infrastructure/`: contenedores y despliegue.
6. `docs/`: arquitectura, API, operación y requisitos.
7. `scripts/`: utilidades de desarrollo.
8. `tests/`: pruebas de punta a punta.

## Módulos previstos

- Autenticación y roles por sucursal.
- Ventas, cobros, caja, tickets y devoluciones.
- Catálogo, inventario, compras y proveedores.
- Clientes y crédito.
- Facturación CFDI mediante PAC.
- Pagos con Clip.
- Reportes, auditoría, sincronización y respaldos.

Esta es una estructura de carpetas; los módulos aún no contienen implementación. Los archivos `.gitkeep` permiten conservar carpetas vacías en Git.
