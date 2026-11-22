# Sprint 4: flujos mínimos para probar

## Dónde entrar

- Web, administrador de empresa o nutricionista: Inicio → **Seguimiento y mensajes**.
- Web, paciente: Perfil → **Seguimiento y mensajes**.
- Android: Perfil → **Seguimiento y mensajes**.
- Superadmin: Inicio de la consola de plataforma, filtros e incidencias.

## CU-19: evolución y adherencia

Registrar dos mediciones con fechas distintas y consultar el período. La tabla conserva peso, talla, IMC, autor y fecha; el gráfico muestra la secuencia de peso. Las mediciones históricas empiezan con los registros nuevos: no se inventan valores anteriores desde la anamnesis actual.

La primera métrica es adherencia **al registro de comidas**, no cumplimiento clínico de nutrientes: `100 × suma diaria de min(registros, meta) / suma de metas`. La meta es la cantidad de comidas del plan aprobado para ese día, o la configuración de empresa si no había plan. Las comidas extra no compensan otro día; se muestran los días sin registros. Antes del alta de la cuenta no se exige una meta. Todos los días se agrupan en horario Bolivia.

Al consultar, se evalúa inactividad por falta de registros de comida y mediciones; si supera el umbral, se muestra la alerta y se genera una notificación deduplicada. No es un monitor en segundo plano. Cada evaluación guarda período, fórmula, resultados y copia de los parámetros; el historial permite volver a abrirla sin recalcular.

## CU-20: revisión profesional

Seleccionar paciente, cargar planes y elegir un borrador IA. Se puede corregir el texto de indicaciones, aprobar/asignar o rechazar, siempre con motivo. Se guardan autor, fecha, decisión y valores antes/después. El editor de planes existente también registra sus modificaciones y aprobaciones. Aprobar conserva el mecanismo existente: un plan vigente por paciente, archivo del anterior y notificación. El alcance mínimo es revisión de planes nutricionales IA; el chat Carlitos continúa como orientación conversacional.

## CU-21: mensajes humanos

Paciente y nutricionista deben tener vínculo `LINKED` en la misma empresa. Cada uno selecciona al otro en Mensajes, escribe y envía. El destinatario recibe una notificación sin el contenido privado y puede abrir el historial. Hay actualización manual y paginación de 50 mensajes; no se promete lectura en tiempo real ni doble check. Desvincular bloquea el acceso al hilo.

## CU-22: parámetros versionados

En Parámetros, el profesional puede modificar comidas/día sin plan, días de inactividad, agua (L/día) y sueño (h/día), con rangos y motivo. Cada cambio genera una versión de empresa con autor y fecha. Los hábitos evaluados y los avisos semanales usan las metas de agua/sueño de esa empresa. Las evaluaciones guardadas retienen su configuración original.

## CU-23: importación CSV

Descargar plantilla, reemplazar la fila de ejemplo y cargar el archivo UTF-8. Columnas obligatorias: `full_name,email,password`; opcional: `phone`. Máximo 100 pacientes y 1 MB. Cada contraseña requiere 8 caracteres, mayúscula, minúscula, número y símbolo. No se envían correos automáticamente ni se muestran las contraseñas en la vista previa.

Analizar muestra aceptadas y errores por fila, sin crear cuentas. Confirmar durante 15 minutos incorpora solo filas válidas, vuelve a comprobar duplicados/cupo/sucursal y muestra altas y rechazos. Repetir la confirmación devuelve el mismo resultado sin duplicar. Se usa la empresa y sucursal activa del usuario. Si importa un nutricionista, se vinculan a él los pacientes nuevos. Cancelar antes de confirmar no crea pacientes.

## CU-24: consola del superadmin

Filtrar empresa y período de altas. Las tarjetas muestran empresas y suscripciones creadas en ese período y su estado **actual**; no reconstruyen cómo estaban en una fecha histórica. Se informa fecha de actualización y definición del filtro. Las incidencias muestran errores inesperados 500 registrados por la API con método, plantilla de ruta, clase del error y estado; se pueden resolver con una nota. Son globales y solo admiten filtro por fecha. No se guardan cuerpos, consultas, mensajes ni datos clínicos en esas incidencias.

## Despliegue

La migración `20261122_10` agrega las tablas sin borrar datos anteriores. Railway ya usa `python prepare_db.py` como paso previo al despliegue, que aplica Alembic antes de arrancar. No se requieren variables nuevas ni servicios nuevos. Publicar backend primero, luego web, y distribuir la APK actualizada. Las cuentas/empresas conservan su configuración y los nuevos módulos empiezan sin registros ficticios.
