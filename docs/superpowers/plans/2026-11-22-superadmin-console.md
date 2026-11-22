# Superadmin Console Implementation Plan

**Goal:** Una consola web sencilla para gestionar empresas, planes comerciales y suscripciones, sin acceso a datos operativos de las empresas.

**Architecture:** Reutilizar `SUPERADMIN`, separar su vista de la clínica y ofrecer endpoints administrativos bajo `/api/v1/platform`. Las empresas siguen siendo tenants; el catálogo de planes comerciales pasa de `PLANS` a la base de datos conservando códigos e historial existentes.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Angular 22, Railway y Vercel.

**Spec:** Requisitos acordados en este chat: menú corto, empresas activas/inactivas, plan de cada empresa, creación de planes y ausencia de acceso a pacientes, citas, recetas, caja y reportes internos.

## Alcance y reglas

- Menú: Inicio, Empresas, Planes, Suscripciones e Historial de cambios. Perfil y cerrar sesión.
- Empresas: nombre, administrador de contacto, cantidad de sucursales, estado y plan vigente. Sin selector para entrar al espacio operativo.
- El estado activo/inactivo de la empresa y el estado de su suscripción se muestran separados.
- Planes comerciales: nombre, código, precio, moneda, duración, límites de pacientes/sucursales y funciones ya soportadas. Publicar o archivar; no borrar planes contratados.
- Las condiciones de una suscripción contratada se conservan. Cambiar el precio de catálogo aplica a contrataciones posteriores.
- Asignar un plan manualmente requiere motivo y vigencia; no genera pagos ni comprobantes de PayPal ficticios.
- Suspender una empresa bloquea su operación conservando sus datos y sesiones sujetas al control de acceso del servidor.
- Esta entrega comprende backend, migración de DB y web. No requiere cambiar la interfaz móvil ni generar APK; se verifica compatibilidad de la API compartida.

## Riesgos que deben probarse

1. Un SUPERADMIN intenta acceder directamente a una API clínica o usar `X-Report-Client: mobile`: se rechaza.
2. Un administrador de empresa intenta abrir la consola o modificar planes globales: se rechaza.
3. Migrar el catálogo o editar precios modifica una suscripción/pago histórico: debe conservarse intacto.
4. Suspender/reactivar y asignar planes deben dejar historial sin fabricar ingresos.
5. Un nuevo plan publica límites o funciones que no se aplican: los límites deben validarse en el backend y las funciones limitarse al catálogo soportado.

## 1. Separar permisos y navegación

**Modificar backend:** `app/api/deps.py`, `app/core/authorization.py`, `app/core/workspace.py`, `app/api/v1/router.py`.

**Modificar web:** `src/app/app.routes.ts`, `src/app/core/guards/auth.guard.ts`, `src/app/features/auth/login/login.component.ts`, `src/app/features/dashboard/staff-navigation.model.ts`.

- [ ] Añadir pruebas de rechazo a endpoints operativos con cuenta SUPERADMIN y de rechazo del panel con cuenta ADMIN_ORGANIZATION.
- [ ] Aplicar una lista explícita de rutas permitidas para SUPERADMIN: consola y su propia autenticación/perfil. Retirar privilegios clínicos y cambios de espacio operativo.
- [ ] Enviar al SUPERADMIN a `/platform`; impedir que abra `/dashboard`. Mantener el dashboard de clínicas para sus roles.
- [ ] Verificar que llamadas iniciales, enlaces directos y cabeceras no permitan saltar las restricciones.

## 2. Guardar los planes comerciales en DB

**Crear:** `app/models/commercial_plan.py`, `app/schemas/platform.py`, `app/services/platform_service.py` y una migración en `alembic/versions/` con identificador generado al implementar.

**Modificar:** `app/models/__init__.py`, `app/services/subscription_service.py`, `app/api/v1/subscriptions.py`, `app/models/subscription.py` y los consumidores de `PLANS` localizados por búsqueda.

- [ ] Crear catálogo con código único, nombre, precio decimal, moneda, duración, límites, funciones y estado publicado/archivado.
- [ ] Migrar Básico, Profesional y Premium conservando códigos, precios y suscripciones existentes. Mantener compatibles los planes personales del cliente.
- [ ] Conservar una copia de precio y condiciones en cada contratación para evitar cambios retroactivos.
- [ ] Conectar listado público, checkout y aplicación de límites con el catálogo persistido. No aceptar desde el cliente un precio distinto del catálogo.
- [ ] Probar catálogo inválido, plan archivado, renovación y compatibilidad de comprobantes existentes.

## 3. Crear la API administrativa

**Crear:** `app/api/v1/platform.py`. Usar `app/services/platform_service.py` y `app/schemas/platform.py`.

**Interfaces previstas:**

- `GET /platform/overview`: cifras administrativas de empresas/suscripciones.
- `GET /platform/companies` y `GET /platform/companies/{id}`: ficha administrativa y plan.
- `PATCH /platform/companies/{id}/status`: estado y motivo.
- `GET /platform/plans`, `POST /platform/plans`, `PATCH /platform/plans/{id}`: catálogo y publicación/archivo.
- `GET /platform/subscriptions`: suscripciones de empresas, filtros y paginación.
- `PUT /platform/companies/{id}/subscription`: asignación administrativa con motivo y vigencia.
- `GET /platform/audit`: historial exclusivamente de acciones de plataforma.

- [ ] Respuestas con campos explícitos; no reutilizar respuestas que incluyan información de pacientes o caja.
- [ ] Registrar actor, fecha, empresa y cambios anterior/nuevo en un historial de plataforma separado de la bitácora clínica.
- [ ] Validar estados, fechas, precios, códigos y límites; rechazar duplicados y planes archivados.
- [ ] Comprobar suspensión con una sesión de empresa ya iniciada y reactivación sin pérdida de datos.

## 4. Crear la consola web

**Crear carpeta:** `src/app/features/platform/` con `platform-shell.component.ts`, `platform-overview.component.ts`, `platform-companies.component.ts`, `platform-plans.component.ts`, `platform-subscriptions.component.ts`, `platform-audit.component.ts` y `platform.service.ts`.

- [ ] Construir un menú de cinco opciones y una tabla de empresas con búsqueda/filtros.
- [ ] Mostrar ficha de empresa en panel/modal: datos administrativos, administrador, cantidad de sucursales, estado y suscripción.
- [ ] Añadir formularios pequeños para crear/editar planes y asignar suscripción.
- [ ] Mostrar confirmación y motivo al cambiar estado; deshabilitar doble envío y presentar errores claros.
- [ ] Mantener estados de carga, vacío y error; verificar diseño en navegador de escritorio y pantalla estrecha.

## 5. Probar y desplegar

- [ ] Ejecutar pruebas de permisos, catálogo, historial, suspensión y suscripciones existentes.
- [ ] Probar login y navegación de SUPERADMIN y ADMIN_ORGANIZATION; comprobar que las URLs operativas quedan bloqueadas al primero.
- [ ] Ejecutar build web completo, incluida verificación de integridad de la PWA.
- [ ] Publicar backend y aplicar migración en Railway; comprobar DB, catálogo y endpoints administrativos.
- [ ] Publicar front en Vercel y verificar login → empresas → crear plan → asignar plan → cambiar estado → historial.
- [ ] Entregar la cuenta de prueba SUPERADMIN y los links, con resultados comprobados.

**Criterio de terminado:** el SUPERADMIN administra empresas y planes desde una consola corta y no puede leer ni modificar información operativa de una empresa, tampoco llamando directamente a la API. Las cuentas de empresa y sus suscripciones existentes siguen funcionando.
