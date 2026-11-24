# Carlitos profesional — pacientes y recetas

## Uso

Web → Atención nutricional → **Carlitos · Asistente**. Disponible para `ADMIN_ORGANIZATION` y `NUTRICIONISTA`. El superadmin conserva exclusivamente la consola de plataforma.

1. Seleccionar empresa/sucursal de trabajo y abrir el único chat.
2. Escribir «Buscá al paciente Alex». Ante coincidencias, responder el número o nombre completo; si hay una sola, «sí» la selecciona.
3. Seguir con «Mostrame su anamnesis». La ficha completa se muestra directamente desde el backend autorizado. También podés preguntar «¿está vinculado?», «¿conmigo?», «¿qué alergias tiene?» o «¿qué recetas ya tiene?»: Gemini elige la consulta, el backend valida permisos y obtiene los datos, y Gemini redacta con ese resultado.
4. «Recomendale una cena» muestra hasta tres recetas existentes, con foto, ingredientes, porción, motivos y advertencias. «Otra opción» conserva paciente y categoría y excluye las anteriores.
5. «Asignale la segunda» prepara la confirmación. Solo responder «confirmo» al pedido de confirmación guarda la asignación, bitácora y notificación al paciente en la misma transacción. La app muestra «Nueva receta en tu plan», con acceso a Ver plan; el mecanismo existente envía push después del commit cuando Firebase y el dispositivo están configurados. Repetir la confirmación no duplica el aviso. «No» descarta. También hay botones dentro de los mensajes; usan el mismo chat.
6. «Nuevo chat» borra el contexto. Los resultados y preguntas quedan en la conversación (hasta 20 intercambios visibles), sin formularios separados de búsqueda/recomendación.

Las restricciones se toman de la anamnesis; no se agregan nuevas restricciones a partir de la conversación en esta versión. La consulta de citas está disponible por estado y fechas. Aceptar/cancelar citas, enviar mensajes, ejecutar informes, pagos y edición clínica todavía no se ejecutan desde el chat.

## Separación y consumo

- `GEMINI_STAFF_API_KEY`: clave privada exclusiva de este módulo, únicamente en Railway/backend. Si falta o falla, no utiliza `GEMINI_API_KEY` ni cambia de modelo automáticamente.
- `GEMINI_STAFF_MODEL=gemini-3.5-flash-lite`. Pensamiento mínimo, temperatura 0, JSON estructurado y salida máxima de 256 tokens.
- Máximo 800 caracteres por mensaje. Los pedidos de acción usan una interpretación; las preguntas de datos usan hasta dos llamadas (interpretación y respuesta fundamentada). Solo se envían las instrucciones del intérprete, el texto que escribió el usuario y metadatos mínimos de interfaz (paciente seleccionado sí/no, número de opciones, categoría y confirmación pendiente). No se agrega la anamnesis, catálogo ni historial completo al prompt del intérprete. Para redactar una respuesta se envía únicamente el resultado necesario de la herramienta autorizada: vínculos activos, sección consultada de anamnesis, recetas asignadas o motivos de propuestas. No se envían correos, códigos de emparejamiento, contraseñas, IDs internos ni el resto de la ficha. Solo se leen fichas con consentimiento.
- Abrir el módulo no llama a Gemini. Respuestas breves reconocidas («sí», números, «asignale la segunda», «otra opción», «confirmo», «no») se resuelven localmente. Los pedidos libres usan una interpretación de Gemini.
- Si falla la redacción, se devuelve un resumen de los hechos consultados, sin convertirlo en ayuda genérica. Las preguntas son de solo lectura y no pueden ejecutar asignaciones.
- Tiempo de espera HTTP: 9 s, conexión 2 s y espera de pool 1 s. Una llamada, sin reintentos automáticos. Un error conserva el mensaje para reintentar.
- Límite en memoria: seis interpretaciones/minuto por profesional y treinta/minuto por empresa, por proceso del servidor. Esto limita frecuencia, no constituye un tope monetario ni certifica el saldo disponible del proyecto Google.
- El endpoint devuelve uso real reportado por Gemini; los logs contienen únicamente modelo, tokens y duración, sin texto del usuario ni ficha clínica.

Documentación de Google: [salidas estructuradas](https://ai.google.dev/gemini-api/docs/structured-output), [Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite), [razonamiento mínimo](https://ai.google.dev/gemini-api/docs/thinking), [límites](https://ai.google.dev/gemini-api/docs/rate-limits). Las cuotas de Google son por proyecto, aunque se usen claves distintas.

## Filtros y autorización

El backend consulta hasta cien recetas activas de la empresa/sucursal o del catálogo compartido de esa misma empresa. Aplica la categoría pedida y excluye recetas ya asignadas o descartadas en esa búsqueda. Excluye coincidencias de alérgenos conocidos y mezclas ambiguas cuando hay alergias; contempla celiaquía/gluten, preferencias vegetarianas/veganas y sodio declarado para hipertensión. Alergias no interpretables bloquean propuestas hasta revisión manual. La prioridad usa objetivo, proteína, calorías y fibra del catálogo; no es un diagnóstico ni un porcentaje de seguridad clínica.

Una ficha ausente o sin consentimiento no permite recomendar. La aprobación profesional sigue siendo necesaria: estos filtros no evalúan todas las condiciones clínicas posibles ni ajustan automáticamente porciones o medicamentos.

El contexto de conversación firmado dura veinte minutos y queda ligado al profesional, sesión, empresa y sucursal. No contiene anamnesis ni historial textual. El frontend devuelve este contexto sin modificarlo; IDs y opciones los valida el servidor. Cada tarjeta se relaciona con una propuesta firmada de cinco minutos ligada a autor, sesión, empresa, sucursal, paciente, receta y huellas de ficha/catálogo. Al confirmar se revalidan permisos y estado y se bloquean paciente, receta y ficha durante la transacción. Repetir una confirmación devuelve la asignación existente; un token procesado no restaura una asignación retirada después. La bitácora identifica la operación, sin copiar la anamnesis.

Cambiar de espacio borra el contexto del componente y cancela solicitudes pendientes. El servidor rechaza una propuesta del espacio anterior. Al consultar recetas, la lista de pacientes asignados que recibe un cliente contiene solo su propio ID; no los IDs de otros pacientes del catálogo compartido.

## Preguntas y contexto

«¿Está vinculado?» consulta vínculos LINKED del paciente y profesionales activos de la misma empresa/sucursal. «¿Conmigo?» distingue el usuario actual de otros profesionales. Se excluyen vínculos pendientes/cancelados/expirados y no se exponen códigos ni notas privadas. Si hay varios candidatos, se pide elegir y después se retoma la pregunta original. Las preguntas sobre alergias, objetivos, hábitos, medicación, anamnesis y recetas se resuelven con herramientas de lectura acotadas. La explicación de propuestas no reemplaza la revisión profesional.

## API

- POST `/api/v1/staff-assistant/chat`: `message`, `context_token?`. Devuelve el mensaje, resultados estructurados y nuevo contexto firmado. Es el único endpoint usado por el chat web.
- GET `/api/v1/staff-assistant/patients?search=Alex&offset=0`: diez candidatos, con `has_more`.
- POST `/api/v1/staff-assistant/query`: `message`, `patient_id?`, `intent?` (`recommend`/`patients`, accesos rápidos), `meal?`, `exclude_recipe_ids` (hasta 32).
- POST `/api/v1/staff-assistant/confirm`: únicamente `proposal_token`.

Las imágenes y asignaciones se consultan mediante las APIs existentes de recetas; no requiere una nueva APK. No hay migraciones de esquema.

## Verificación

Pruebas backend en `tests/test_staff_conversation.py` y `tests/test_staff_assistant.py`, más catálogo compartido y recetas/clínica existentes. Pruebas web en `staff-assistant.component.spec.ts` y navegación del dashboard. Build de producción con `API_BASE_URL` del backend. Los tests simulan Gemini y comprueban que nunca reciben la clave general. La prueba de conexión real usó un pedido genérico sobre un paciente demo; no se enviaron fichas clínicas.


## Agenda conversacional

«Mostrame mis citas pendientes» consulta PENDING (pendientes de aceptación), sin mezclarlas con ACCEPTED (aceptadas pendientes de pago) ni CONFIRMED. El administrador consulta todas las citas de la sucursal activa; el nutricionista solo las que atiende. «Sus citas» o «las citas de Alex» filtra además por el paciente autorizado; una consulta de mi agenda no se restringe por el paciente que quedó seleccionado anteriormente.

Ejemplos: «Mostrame mis citas confirmadas», «Mostrame las citas pendientes del 1 al 15 de noviembre de 2026», «Mostrame las citas de Alex de hoy». Gemini recibe la fecha actual de Bolivia y traduce los límites a fechas ISO; el backend aplica los días inclusivos en UTC-4. Sin fechas se consultan todos los períodos y se informa ese alcance. Se muestran hasta diez citas ordenadas por fecha, el total real y aviso si quedan más. Las filas se agregan desde el resultado del backend, sin depender de que Gemini enumere correctamente todos los registros. No se envían motivos clínicos ni notas al proveedor.

Esta función es de solo lectura: preguntar por citas no acepta, cancela, cobra ni completa ninguna cita. Los cambios necesarios están únicamente en backend; web y mobile no requieren nueva compilación para mostrar estos mensajes.
