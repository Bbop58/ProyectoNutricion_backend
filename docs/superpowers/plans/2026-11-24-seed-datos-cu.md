# Datos demo para probar los CU — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completar los datos ficticios antes de desarrollar Carlitos profesional.
**Architecture:** Extender el seeder determinista existente con un módulo de perfiles clínicos sintéticos y otro de recetas. Conservar filas existentes, estados revisados, contraseñas, pagos y aislamiento de empresas/sucursales. Ejecutar una vez en predeploy de Railway y restaurar el comando habitual.
**Tech Stack:** Python, SQLAlchemy, pytest, PostgreSQL/Railway.
**Spec:** Pedido del usuario del 24/11/2026: primero seeders, con datos considerables para los CU implementados.

## Global Constraints
- Solo cuentas demo identificadas por sus claves estables; no modificar pacientes reales.
- Conservar toda anamnesis existente y las modificaciones profesionales posteriores.
- Datos clínicos explícitamente ficticios. No llamar Gemini, PayPal, Brevo ni Firebase al sembrar.
- Planes nutricionales únicamente DRAFT; nunca simular aprobaciones profesionales o pagos reales.
- Respetar los planes: recetario en Profesional/Premium; Básico conserva sus restricciones.

## Review Focus
- Segunda ejecución: cero duplicados y cero reposición de borradores ya revisados.
- Ficha existente: conservarla íntegra, sin inventarle historia clínica contradictoria.
- Fechas: mediciones posteriores al alta y anteriores al cierre histórico del 22/11/2026.
- Aislamiento: paciente, profesional, ficha, borrador y mensajes de la misma empresa/sucursal.
- Recomendaciones: ingredientes explícitos y sodio estimado para los nuevos ejemplos; un catálogo demo no equivale a prescripción ni garantiza compatibilidad clínica.

### Task 1: Datos y pruebas
**Files:** crear `app/seeders/demo_care.py`, `app/seeders/demo_recipes.py`, `tests/test_demo_care_seeder.py`; modificar `app/seeders/demo_business.py`, `tests/test_demo_business_seeder.py`, `seed_demo_business.py`.
**Interfaces:** `ensure_demo_patient_care(db, patient, nutritionist, patient_number, joined_at, period_end, report)` y `ensure_demo_configuration(db, tenant, admin, report)`; `EXTRA_DEMO_RECIPES` contiene 24 recetas adicionales compatibles con `DemoRecipe`.
- [ ] Probar 159 fichas en una base vacía, 3 mediciones por ficha nueva, 159 notas clínicas ficticias, 159 borradores y 318 mensajes internos demo; configuración inicial por empresa si no existe.
- [ ] Ampliar de 8 a 32 recetas por cada una de las 3 empresas con recetario: 96 recetas totales, compartidas dentro de su empresa.
- [ ] Probar preservación de ficha existente, revisión posterior de borrador e idempotencia; mantener ingresos históricos originales.
- [ ] Agregar CSV listo para probar importación en Vitalia: filas válidas, duplicada e inválida. No confirmar importaciones automáticamente.

### Task 2: Carga y comprobación real
**Files:** actualizar `docs/SEEDER_DEMO_EMPRESAS.md`, crear `docs/PRUEBAS_CU_DATOS_DEMO.md`.
- [ ] Ejecutar pytest de ambos seeders y catálogos compartidos.
- [ ] Commit y push únicamente backend. Configurar temporalmente predeploy: preparación DB + seeder con autorización explícita de producción.
- [ ] Verificar logs de carga y consultar API con administradores de las 5 empresas para comprobar fichas, mediciones, borradores, mensajes y recetas en todas las sucursales.
- [ ] Restaurar predeploy a `python prepare_db.py`. Registrar conteos reales y pasos de prueba web/móvil.

## Fuera de esta entrega
Chat profesional, nueva configuración Gemini, correcciones de asignación de recetas y optimización del recomendador: después de terminar y verificar los datos. CU24 usa empresas y planes existentes; no se fabrican incidentes de producción.
