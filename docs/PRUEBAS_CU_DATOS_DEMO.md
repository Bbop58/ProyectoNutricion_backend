# Probar los CU con los datos demo

Primero seleccionar la empresa/sucursal correcta. Cada paciente demo está vinculado al nutricionista de su sucursal. Los administradores trabajan en la sucursal seleccionada; los nutricionistas en sus pacientes vinculados. Superadmin usa exclusivamente su consola de empresas.

## Cuentas de referencia: Vitalia

- Web administrador: `admin.vitalia@example.test`.
- Web nutricionista de sucursal principal: `nutritionist.vitalia.01@example.test`.
- Móvil paciente: `patient.vitalia.001@example.test` (Alex Demo VITALIA 001, sucursal principal).
- Las contraseñas existentes no cambian; se usa la contraseña demo ya entregada/configurada, sin guardarla en este documento.
- Mismos patrones para `vidasana`, `nutrifit`, `equilibrio`, `andina`. `.01` y paciente `.001` pertenecen a la sucursal principal de cada empresa.

| CU | Plataforma y recorrido | Datos/resultado a comprobar |
|---|---|---|
| 19 Seguimiento | Web admin/nutricionista → Seguimiento y mensajes → seleccionar paciente → consultar desde su alta hasta 22/11/2026. Móvil paciente → seguimiento, mismo período. | Tres mediciones, curva de peso, hábitos y registros manuales de comidas. La adherencia mide registros, no calidad clínica; hay días sin registros deliberadamente. |
| 20 Revisión de plan | Web nutricionista/admin → paciente → planes/seguimiento → abrir el borrador con título DEMO SINTÉTICO. | Corregir indicaciones con motivo, rechazar o aprobar. Debe registrar la revisión; solo tras aprobar puede verlo el paciente en móvil → Mi plan. No regenerar con IA para encontrar este borrador. |
| 21 Mensajes | Web nutricionista → Seguimiento y mensajes → paciente vinculado; móvil paciente → su conversación con el nutricionista. | Dos mensajes demo iniciales. Enviar uno nuevo y pulsar Actualizar en la otra cuenta para comprobar comunicación real dentro de la app. El administrador puede conversar también, pero el historial demo inicial corresponde al nutricionista vinculado. |
| 22 Parámetros | Web admin/nutricionista → Parámetros. | Ver configuración inicial o la que ya tenía la empresa. Cambiar una meta indicando motivo: debe aparecer una nueva versión. |
| 23 Importación | Web admin de Vitalia → Importación → cargar `docs/fixtures/importacion_cu23_vitalia.csv` → Analizar. | Antes de importar por primera vez: dos válidas y dos rechazadas. Confirmar crea únicamente las dos válidas; repetir detecta sus correos existentes. No se enviará correo automáticamente. |
| 24 Supervisión | Web superadmin → empresas/planes/indicadores. | Cinco empresas demo con sus planes y estados reales. Filtrar estado/fecha según el dato registrado. Incidencias puede estar vacío; no se generan errores falsos para llenar el panel. |
| Recetas | Web admin/nutricionista → Recetas → seleccionar un paciente y abrir recomendador existente. | 32 recetas de su empresa en Equilibrio, Andina y Vitalia, desde cualquiera de sus sucursales. Comparar perfiles diferentes y alertas. VidaSana/NutriFit son Básico y no incluyen recetario; su catálogo demo permanece vacío. |

El recomendador actual usa reglas locales; el chat profesional con la nueva clave Gemini es una etapa posterior. La existencia de fixtures no certifica el correcto funcionamiento de cada acción: la verificación de esta entrega cubre carga, relaciones, aislamiento, repetición y lectura por API. La asignación de recetas compartidas tiene una validación pendiente de revisar antes de desarrollar el chat.
