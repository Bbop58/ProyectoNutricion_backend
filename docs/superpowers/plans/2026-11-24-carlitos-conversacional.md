# Carlitos en un único chat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar los formularios de Carlitos por una conversación continua que permita buscar, elegir paciente, leer anamnesis, recomendar, cambiar opciones y confirmar asignación escribiendo.
**Architecture:** Nuevo endpoint conversacional con contexto firmado y acotado, ligado al profesional/empresa/sucursal. Reutilizar filtros y asignación existentes. Gemini solo extrae intención; confirmaciones y referencias claras se resuelven localmente. Angular conserva hasta veinte turnos y presenta resultados dentro de cada respuesta.
**Tech Stack:** FastAPI, jose, Pydantic, Angular 22 signals.
**Spec:** Conversación aprobada por el usuario: buscar Alex → sí → mostrar anamnesis → recomendar cena → otra opción → asignar segunda → confirmo.

## Global Constraints
- Un solo campo de escritura, sin formulario independiente de búsqueda ni botones de herramientas separados.
- Mantener permisos, filtros clínicos, caducidad de propuesta y auditoría existentes.
- Nunca guardar por una clasificación del modelo: «confirmo» requiere propuesta pendiente de un turno anterior y confirmación explícita.
- Contexto firmado: autor, sesión, empresa y sucursal; veinte minutos de contexto, cinco minutos por propuesta.
- No enviar ficha, nombres de candidatos ni historial completo al proveedor. A lo sumo metadatos de contexto sin datos clínicos.

## Review Focus
- Nombres repetidos o referencias ambiguas: preguntar antes de elegir.
- Cambio de paciente: eliminar propuestas/peticiones pendientes anteriores.
- Contexto o propuesta alterados, expirados o de otra sucursal: rechazar.
- «Confirmo» sin pendiente y «asigná y confirmá» en un solo turno: no guardar.
- Historial visible: opciones anteriores quedan informativas; solo las del turno activo permiten continuar con botones opcionales.

### Task 1: Conversación backend
**Files:** crear `app/services/staff_conversation.py`, `tests/test_staff_conversation.py`; modificar esquema, intérprete y router de Carlitos.
**Interface:** POST `/staff-assistant/chat` recibe `message`, `context_token?`; devuelve respuesta, resultados y nuevo `context_token`.
- [ ] Probar flujo completo, resumen de ficha, homónimos, otras opciones, selección ordinal y confirmación separada.
- [ ] Probar contexto ajeno/alterado, cancelación, cambio de paciente y permisos reevaluados.
- [ ] Reutilizar asignación idempotente y no invocar Gemini para confirmaciones/alternativas claras.

### Task 2: Chat web y despliegue
**Files:** sustituir componente Angular de Carlitos y sus pruebas; actualizar documentación de uso.
- [ ] Resultados, fichas, tarjetas y confirmación dentro de la conversación; un único formulario y campo de texto.
- [ ] Cancelar respuestas tardías al cambiar de espacio; conservar errores recuperables y máximo veinte turnos.
- [ ] Pruebas, build, push backend/web y verificación del diálogo completo en Vercel con datos demo.
