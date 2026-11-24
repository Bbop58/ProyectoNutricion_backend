# Carlitos profesional — pacientes y recetas

## Uso

Web → Atención nutricional → **Carlitos · Asistente**. Disponible para `ADMIN_ORGANIZATION` y `NUTRICIONISTA`. El superadmin conserva exclusivamente la consola de plataforma.

1. Seleccionar empresa/sucursal de trabajo y abrir el único chat.
2. Escribir «Buscá al paciente Alex». Ante coincidencias, responder el número o nombre completo; si hay una sola, «sí» la selecciona.
3. Seguir con «Mostrame su anamnesis». La ficha se consulta en el backend autorizado, sin enviarla al modelo.
4. «Recomendale una cena» muestra hasta tres recetas existentes, con foto, ingredientes, porción, motivos y advertencias. «Otra opción» conserva paciente y categoría y excluye las anteriores.
5. «Asignale la segunda» prepara la confirmación. Solo responder «confirmo» al pedido de confirmación guarda la asignación y bitácora. «No» descarta. También hay botones dentro de los mensajes; usan el mismo chat.
6. «Nuevo chat» borra el contexto. Los resultados y preguntas quedan en la conversación (hasta 20 intercambios visibles), sin formularios separados de búsqueda/recomendación.

Las restricciones se toman de la anamnesis; no se agregan nuevas restricciones a partir de la conversación en esta versión. Citas, mensajes, informes, pagos y edición clínica no se ejecutan desde el chat.

## Separación y consumo

- `GEMINI_STAFF_API_KEY`: clave privada exclusiva de este módulo, únicamente en Railway/backend. Si falta o falla, no utiliza `GEMINI_API_KEY` ni cambia de modelo automáticamente.
- `GEMINI_STAFF_MODEL=gemini-3.5-flash-lite`. Pensamiento mínimo, temperatura 0, JSON estructurado y salida máxima de 192 tokens.
- Una llamada por pedido escrito, máximo 800 caracteres. Solo se envían las instrucciones del intérprete, el texto que escribió el usuario y metadatos mínimos de interfaz (paciente seleccionado sí/no, número de opciones, categoría y confirmación pendiente). No se agrega la anamnesis, catálogo ni historial de conversaciones al prompt.
- Abrir el módulo no llama a Gemini. Respuestas breves reconocidas («sí», números, «asignale la segunda», «otra opción», «confirmo», «no») se resuelven localmente. Los pedidos libres usan una interpretación de Gemini.
- Tiempo de espera HTTP: 9 s, conexión 2 s y espera de pool 1 s. Una llamada, sin reintentos automáticos. Un error conserva el mensaje para reintentar.
- Límite en memoria: seis interpretaciones/minuto por profesional y treinta/minuto por empresa, por proceso del servidor. Esto limita frecuencia, no constituye un tope monetario ni certifica el saldo disponible del proyecto Google.
- El endpoint devuelve uso real reportado por Gemini; los logs contienen únicamente modelo, tokens y duración, sin texto del usuario ni ficha clínica.

Documentación de Google: [salidas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output), [Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [razonamiento mínimo](https://ai.google.dev/gemini-api/docs/thinking), [límites](https://ai.google.dev/gemini-api/docs/rate-limits). Las cuotas de Google son por proyecto, aunque se usen claves distintas.

## Filtros y autorización

El backend consulta hasta cien recetas activas de la empresa/sucursal o del catálogo compartido de esa misma empresa. Aplica la categoría pedida y excluye recetas ya asignadas o descartadas en esa búsqueda. Excluye coincidencias de alérgenos conocidos y mezclas ambiguas cuando hay alergias; contempla celiaquía/gluten, preferencias vegetarianas/veganas y sodio declarado para hipertensión. Alergias no interpretables bloquean propuestas hasta revisión manual. La prioridad usa objetivo, proteína, calorías y fibra del catálogo; no es un diagnóstico ni un porcentaje de seguridad clínica.

Una ficha ausente o sin consentimiento no permite recomendar. La aprobación profesional sigue siendo necesaria: estos filtros no evalúan todas las condiciones clínicas posibles ni ajustan automáticamente porciones o medicamentos.

El contexto de conversación firmado dura veinte minutos y queda ligado al profesional, sesión, empresa y sucursal. No contiene anamnesis ni historial textual. El frontend devuelve este contexto sin modificarlo; IDs y opciones los valida el servidor. Cada tarjeta se relaciona con una propuesta firmada de cinco minutos ligada a autor, sesión, empresa, sucursal, paciente, receta y huellas de ficha/catálogo. Al confirmar se revalidan permisos y estado y se bloquean paciente, receta y ficha durante la transacción. Repetir una confirmación devuelve la asignación existente; un token procesado no restaura una asignación retirada después. La bitácora identifica la operación, sin copiar la anamnesis.

Cambiar de espacio borra el contexto del componente y cancela solicitudes pendientes. El servidor rechaza una propuesta del espacio anterior. Al consultar recetas, la lista de pacientes asignados que recibe un cliente contiene solo su propio ID; no los IDs de otros pacientes del catálogo compartido.

## API

- POST `/api/v1/staff-assistant/chat`: `message`, `context_token?`. Devuelve el mensaje, resultados estructurados y nuevo contexto firmado. Es el único endpoint usado por el chat web.
- GET `/api/v1/staff-assistant/patients?search=Alex&offset=0`: diez candidatos, con `has_more`.
- POST `/api/v1/staff-assistant/query`: `message`, `patient_id?`, `intent?` (`recommend`/`patients`, accesos rápidos), `meal?`, `exclude_recipe_ids` (hasta 32).
- POST `/api/v1/staff-assistant/confirm`: únicamente `proposal_token`.

Las imágenes y asignaciones se consultan mediante las APIs existentes de recetas; no requiere una nueva APK. No hay migraciones de esquema.

## Verificación

Pruebas backend en `tests/test_staff_conversation.py` y `tests/test_staff_assistant.py`, más catálogo compartido y recetas/clínica existentes. Pruebas web en `staff-assistant.component.spec.ts` y navegación del dashboard. Build de producción con `API_BASE_URL` del backend. Los tests simulan Gemini y comprueban que nunca reciben la clave general. La prueba de conexión real usó un pedido genérico sobre un paciente demo; no se enviaron fichas clínicas.
