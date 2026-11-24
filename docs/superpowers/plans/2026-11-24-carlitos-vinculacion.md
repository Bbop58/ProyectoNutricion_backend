# Consultas conversacionales de vinculación — Implementation Plan

**Goal:** Gemini interpreta preguntas libres, el backend consulta datos autorizados y Gemini redacta la respuesta usando esos resultados. La regresión inicial es «¿está vinculado?».
**Architecture:** Ampliar la intención estructurada con `question`, `topic` y `link_scope` (`team`/`me`). Agregar herramientas de lectura de vínculos, secciones de anamnesis, recetas asignadas y propuestas; una segunda llamada breve redacta respuestas fundamentadas. Resolver referencias inequívocas al paciente seleccionado o candidato único; consultar únicamente vínculos del espacio autorizado y profesionales activos. Conservar los permisos y confirmaciones de escritura actuales.
**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Gemini JSON.
**Spec:** Captura del usuario: «esta vinculado?» devuelve ayuda genérica; se espera respuesta contextual con datos reales.

## Global Constraints
- El intérprete recibe texto y metadatos de contexto. El redactor recibe únicamente el resultado necesario de la herramienta autorizada para esa pregunta; sin claves, códigos de vinculación, IDs internos, correos ni historial completo.
- No exponer códigos de emparejamiento, notas privadas ni pacientes de otras sucursales.
- Un vínculo PENDING/EXPIRED/CANCELLED o de un profesional inactivo no se presenta como activo.
- Consulta solo de lectura: nunca vincular o asignar por preguntar.
- Desplegar únicamente backend; la respuesta usa el mensaje existente del chat web.

## Review Focus
- Paciente elegido y pregunta corta; candidato único sin seleccionar; varios homónimos sin asumir.
- Vinculado a otro profesional frente a «conmigo».
- Cambio de paciente, vínculos extranjeros, vínculos pendientes y profesional inactivo.
- Pregunta que interrumpe una confirmación: un «sí» posterior no guarda una receta anterior.

### Task 1: Intención y consulta autorizada
- [ ] Agregar regresiones en `tests/test_staff_conversation.py` y comprobar el fallo actual.
- [ ] Modificar `app/schemas/staff_assistant.py`, `app/services/staff_gemini.py` y `app/services/staff_conversation.py`: interpretar consultas y resolverlas con una consulta de vínculos y usuarios activos del mismo espacio.
- [ ] Ejecutar pruebas de conversación, intérprete y recetas; actualizar `docs/CARLITOS_PROFESIONAL.md`.
- [ ] Commit, push, Railway y verificación con la pregunta exacta y una paráfrasis IA en datos demo.
