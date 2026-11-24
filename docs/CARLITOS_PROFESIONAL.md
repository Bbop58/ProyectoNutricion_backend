# Carlitos profesional — pacientes y recetas

## Uso

Web → Atención nutricional → **Carlitos · Asistente**. Disponible para `ADMIN_ORGANIZATION` y `NUTRICIONISTA`. El superadmin conserva exclusivamente la consola de plataforma.

1. Seleccionar empresa/sucursal de trabajo.
2. Escribir «Recomendale una cena a Alex», o usar Buscar paciente y después Recomendar receta.
3. Ante nombres repetidos, seleccionar explícitamente una persona. El nutricionista solo ve vinculados activos; el administrador ve pacientes activos de la sucursal seleccionada.
4. Revisar la ficha resumida, foto, ingredientes, preparación, porción, motivos y advertencias de hasta tres recetas existentes.
5. Asignar receta abre la confirmación junto a esa tarjeta. Confirmar asignación guarda `RecipeAssignment` y una entrada de bitácora. No aprueba ni reemplaza un plan nutricional.
6. Ver otras opciones realiza otra búsqueda local. Descartar propuestas no modifica al paciente.

Las restricciones se toman de la anamnesis; no se agregan nuevas restricciones a partir de la conversación en esta versión. Citas, mensajes, informes, pagos y edición clínica no se ejecutan desde el chat.

## Separación y consumo

- `GEMINI_STAFF_API_KEY`: clave privada exclusiva de este módulo, únicamente en Railway/backend. Si falta o falla, no utiliza `GEMINI_API_KEY` ni cambia de modelo automáticamente.
- `GEMINI_STAFF_MODEL=gemini-3.5-flash-lite`. Pensamiento mínimo, temperatura 0, JSON estructurado y salida máxima de 192 tokens.
- Una llamada por pedido escrito, máximo 800 caracteres. Solo se envían las instrucciones del intérprete y el texto que escribió el usuario. No se agrega la anamnesis, catálogo ni historial de conversaciones al prompt.
- Abrir el módulo, buscar pacientes, seleccionar un homónimo, pedir alternativas y confirmar una asignación no llama a Gemini.
- Tiempo de espera HTTP: 9 s, conexión 2 s y espera de pool 1 s. Una llamada, sin reintentos automáticos. Un error devuelve una explicación y permite seguir usando accesos rápidos.
- Límite en memoria: seis interpretaciones/minuto por profesional y treinta/minuto por empresa, por proceso del servidor. Esto limita frecuencia, no constituye un tope monetario ni certifica el saldo disponible del proyecto Google.
- El endpoint devuelve uso real reportado por Gemini; los logs contienen únicamente modelo, tokens y duración, sin texto del usuario ni ficha clínica.

Documentación de Google: [salidas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output), [Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [razonamiento mínimo](https://ai.google.dev/gemini-api/docs/thinking), [límites](https://ai.google.dev/gemini-api/docs/rate-limits). Las cuotas de Google son por proyecto, aunque se usen claves distintas.

## Filtros y autorización

El backend consulta hasta cien recetas activas de la empresa/sucursal o del catálogo compartido de esa misma empresa. Aplica la categoría pedida y excluye recetas ya asignadas o descartadas en esa búsqueda. Excluye coincidencias de alérgenos conocidos y mezclas ambiguas cuando hay alergias; contempla celiaquía/gluten, preferencias vegetarianas/veganas y sodio declarado para hipertensión. Alergias no interpretables bloquean propuestas hasta revisión manual. La prioridad usa objetivo, proteína, calorías y fibra del catálogo; no es un diagnóstico ni un porcentaje de seguridad clínica.

Una ficha ausente o sin consentimiento no permite recomendar. La aprobación profesional sigue siendo necesaria: estos filtros no evalúan todas las condiciones clínicas posibles ni ajustan automáticamente porciones o medicamentos.

Cada tarjeta lleva una propuesta firmada de cinco minutos ligada a autor, sesión, empresa, sucursal, paciente, receta y huellas de ficha/catálogo. Al confirmar se revalidan permisos y estado y se bloquean paciente, receta y ficha durante la transacción. Repetir una confirmación devuelve la asignación existente; un token procesado no restaura una asignación retirada después. La bitácora identifica la operación, sin copiar la anamnesis.

Cambiar de espacio borra el contexto del componente y cancela solicitudes pendientes. El servidor rechaza una propuesta del espacio anterior. Al consultar recetas, la lista de pacientes asignados que recibe un cliente contiene solo su propio ID; no los IDs de otros pacientes del catálogo compartido.

## API

- GET `/api/v1/staff-assistant/patients?search=Alex&offset=0`: diez candidatos, con `has_more`.
- POST `/api/v1/staff-assistant/query`: `message`, `patient_id?`, `intent?` (`recommend`/`patients`, accesos rápidos), `meal?`, `exclude_recipe_ids` (hasta 32).
- POST `/api/v1/staff-assistant/confirm`: únicamente `proposal_token`.

Las imágenes y asignaciones se consultan mediante las APIs existentes de recetas; no requiere una nueva APK. No hay migraciones de esquema.

## Verificación

Pruebas backend en `tests/test_staff_assistant.py`, más catálogo compartido y recetas/clínica existentes. Pruebas web en `staff-assistant.component.spec.ts` y navegación del dashboard. Build de producción con `API_BASE_URL` del backend. Los tests simulan Gemini y comprueban que nunca reciben la clave general. La prueba de conexión real usó un pedido genérico sobre un paciente demo; no se enviaron fichas clínicas.
