# Carlitos profesional — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat web de administrador/nutricionista para localizar pacientes, recomendar recetas del catálogo según su ficha y asignar una propuesta confirmada.
**Architecture:** Gemini clasifica una pregunta breve; consultas, filtros clínicos, propuestas firmadas y asignación transaccional permanecen en el backend. Componente Angular independiente con tarjetas, selección explícita de pacientes y confirmación. Sin migraciones ni cambios móviles.
**Tech Stack:** FastAPI, SQLAlchemy, httpx, jose, Pydantic, Angular 22 signals.
**Spec:** Flujo aprobado en el chat: buscar paciente → proponer receta existente → revisar → confirmar/asignar o descartar; usar exclusivamente la clave Gemini profesional proporcionada.

## Global Constraints
- Clave exclusiva `GEMINI_STAFF_API_KEY`, únicamente Railway/backend; mantener la clave anterior intacta.
- Modelo `gemini-3.5-flash-lite`, pensamiento mínimo, salida JSON ≤192 tokens, pregunta ≤800 caracteres, una llamada sin reintentos automáticos.
- Ninguna anamnesis, receta, historia clínica o conversación completa se envía a Gemini. Los accesos rápidos/alternativas/confirmaciones no llaman IA.
- Administrador de empresa: empresa/sucursal seleccionada. Nutricionista: pacientes vinculados de esa sucursal. Cliente y superadmin sin acceso al módulo.
- Propuestas válidas cinco minutos y ligadas a profesional, empresa, sucursal, paciente, receta y estado de ficha/catálogo.
- Confirmación revalida permisos, ficha y receta; bloqueo del paciente evita duplicados concurrentes; registrar una única asignación/bitácora.
- Citas y envío de mensajes quedan fuera de esta primera entrega; la interfaz explica las acciones disponibles.

## Review Focus
- Pacientes homónimos: mostrar candidatos, nunca adivinar una identidad.
- Cambio de sucursal, ficha, permisos o receta tras la propuesta: rechazar y pedir nueva consulta.
- Alergias reconocidas, celiaquía y preferencias vegetarianas: excluir incompatibles; alergias no interpretables requieren revisión manual.
- Fallo/429 de Gemini: error breve y accesos rápidos operativos, sin cambiar a la clave general ni repetir llamadas.
- Doble clic/reintento de confirmación: una asignación; nunca aceptar IDs inventados por el modelo.

### Task 1: Backend y pruebas
**Files:** crear `app/schemas/staff_assistant.py`, `app/services/staff_gemini.py`, `app/services/staff_assistant_service.py`, `app/api/v1/staff_assistant.py`, `tests/test_staff_assistant.py`; modificar `app/config.py`, `app/api/v1/router.py`, `app/core/workspace.py`, `app/api/v1/recipes.py`.
**Interfaces:** GET `/staff-assistant/patients?search=&offset=`; POST `/staff-assistant/query` (`message`, `patient_id?`, `intent?`, `meal?`, `exclude_recipe_ids`); POST `/staff-assistant/confirm` (`proposal_token`). Consulta devuelve mensaje, candidatos/propuestas, paciente y uso del proveedor.
- [ ] Implementar intérprete JSON estricto y límites por profesional/empresa en memoria por proceso.
- [ ] Implementar consultas autorizadas, filtros locales, tres propuestas y confirmación firmada/transaccional.
- [ ] Permitir asignar recetas compartidas de la misma empresa sin abrir registros de otras sucursales.
- [ ] Probar aislamiento, homónimos, restricciones, token alterado/vencido, cambio de ficha, repetición y presupuesto de Gemini.

### Task 2: Web, validación y despliegue
**Files:** crear `src/app/features/staff-assistant/staff-assistant.component.{ts,html,css,spec.ts}`; modificar navegación y dashboard.
- [ ] Integrar menú Carlitos y chat acotado, tarjetas con fotos/motivos/advertencias y confirmación en dos pasos.
- [ ] Limpiar contexto ante cambio de espacio y descartar respuestas tardías; errores recuperables y estados accesibles.
- [ ] Ejecutar pruebas focalizadas y build de producción; configurar clave/modelo privados en Railway; push backend y web.
- [ ] Comprobar servicio real, métricas de tokens y flujo en navegador sin aprobar cambios financieros ni planes clínicos automáticamente.
