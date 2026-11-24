# Seeder de empresas de demostración

Genera cinco empresas ficticias con actividad entre el 1 de enero y el 22 de noviembre de 2026. Es una tarea manual; el servidor API no carga estas cinco empresas al iniciar.

## Reglas de los datos

- Reutiliza `VIDASANA` si ya existe; crea las otras empresas solo si faltan.
- Usa los planes y precios que define `SubscriptionService.PLANS`: dos empresas Básico con 8 y 10 pacientes, dos Profesional con 32 y 45, y una Premium con 64.
- Asigna 1, 1, 2, 3 y 5 sucursales como tamaños de muestra. Los planes actuales no definen límites de sucursales.
- Registra once periodos sucesivos de 30 días por empresa: diez `REPLACED` y uno `ACTIVE`, que cubre noviembre. Asocia el pago al administrador y a su sucursal principal, siguiendo el ámbito de trabajo que aplica la API a los historiales. Cada periodo genera un recibo **marcado como sandbox** con referencias `DEMO-*`; no llama a PayPal ni representa dinero real. El PDF del recibo advierte que es un pago de prueba.
- Crea cuentas y nombres ficticios con correos `@example.test`, pacientes vinculados, citas completadas y cobros de consulta en efectivo al precio vigente de USD 5.
- Los cobros de consulta se registran como `Payment` completados, asociados a cita, paciente, sucursal y cajero. Así entran en la caja y en las estadísticas de cobros. Las suscripciones y sus recibos quedan asociados al administrador y a su sucursal principal, por lo que aparecen bajo el aislamiento por sucursal de su historial y reportes personales.
- Agrega 32 recetas generales de muestra a cada empresa cuyo plan incluya `Recetario & Macros` (Profesional y Premium): 96 recetas en total, visibles desde todas las sucursales de su empresa. Son recetas de catálogo, sin prescripción individual ni asignaciones automáticas. Las 24 recetas adicionales por empresa tienen ingredientes con cantidades y sodio estimado explícito.
- Cada receta demo nueva enlaza su imagen ilustrativa generada con IA en `recipes.image_url`: 32 imágenes distintas, compartidas solamente por las copias de la misma receta en las tres empresas. Los archivos WebP se publican desde el frontend en `/assets/recipes/demo/`. Para completar únicamente imágenes faltantes o la antigua foto genérica de recetas demo existentes: `python seed_demo_recipe_images.py --allow-production`. No sustituye fotos propias ni recetas renombradas por el profesional.
- Agrega uno o dos registros manuales de comidas por paciente y por mes activo. Son diarios auto-reportados sintéticos; no simulan análisis por foto ni respuestas de Gemini.
- El CLI informa ingresos brutos simulados separados: suscripciones, consultas cobradas y total. Con los planes y precios actuales, la muestra representa USD 1.319,45 en suscripciones y USD 1.760,00 en consultas (USD 3.079,45 brutos en total). No hay un módulo de costos/gastos que permita calcular utilidad neta. Las recargas de wallet son saldo prepagado del paciente y no se cuentan como ingreso de la clínica.
- Es idempotente: las claves estables evitan duplicados. Las empresas, sucursales y cuentas que ya existían no se borran ni se reemplazan.

## Datos clínicos ficticios para CU19–CU24

La extensión del 24/11/2026 crea datos **DEMO SINTÉTICO**, exclusivamente en las cuentas ficticias del seeder. No toma datos de pacientes reales ni llama servicios externos.

- Una anamnesis por paciente demo: 159 en una base nueva. Ocho perfiles adultos variados: pérdida de grasa, masa muscular, intolerancia a lactosa, celiaquía/gluten, hipertensión, diabetes tipo 2, preferencias vegetarianas/alergia a maní y nueces, y alergia a huevo/pescado con reflujo. Biometría, objetivos, hábitos y preferencias válidos según el esquema actual.
- El consentimiento `true` pertenece al personaje ficticio de prueba; no acredita consentimiento de ninguna persona real. Cada ficha se identifica como sintética en medicación y se acompaña de una nota clínica explícitamente ficticia.
- Tres mediciones históricas por ficha nueva: 477 en una base nueva. Entre el alta del paciente y el 22/11/2026, con evolución moderada y peso final consistente con la ficha. No se reconstruye historia para fichas ya completadas manualmente.
- Una nota clínica ficticia y un borrador nutricional por paciente nuevo del módulo: hasta 159 de cada uno. Los borradores son plantillas de comidas para corregir/rechazar/aprobar en CU20, **no resultados de Gemini ni prescripciones aprobadas**. Todos requieren revisión especial y se identifican como demo en título y notas.
- Dos mensajes internos ficticios por paciente con su nutricionista vinculado: hasta 318 mensajes. Permiten abrir conversaciones de CU21; no disparan correo, push ni notificaciones externas.
- Configuración inicial versionada para CU22 por empresa si aún no existe. Si existe una configuración profesional, se conserva.
- CSV de prueba CU23: [importacion_cu23_vitalia.csv](fixtures/importacion_cu23_vitalia.csv). No se importa automáticamente; contiene dos filas válidas, una repetida dentro del archivo y una inválida.
- CU24 utiliza las cinco empresas, sus planes y estados existentes. No fabrica incidentes del servidor ni suspende empresas para decorar estadísticas.

Toda anamnesis cargada manualmente se conserva sin cambios y se omiten sus fixtures clínicos derivados. Reejecutar el seeder conserva mediciones existentes, decisiones profesionales, conversaciones editadas y recetas editadas; no crea otro borrador si el demo ya fue aprobado o rechazado. Los conteos de producción dependen de lo que ya exista. El catálogo base de alimentos y parámetros del sistema experto se carga por `prepare_db.py`.

## Ejecución

Primero aplica las migraciones y catálogos que usa el backend:

```powershell
python prepare_db.py
```

Después define una contraseña para las nuevas cuentas de demostración y ejecuta el comando:

```powershell
$env:DEMO_BUSINESS_SEED_PASSWORD = 'usa-una-clave-de-prueba-segura'
python seed_demo_business.py
```

Todas las cuentas nuevas comparten esa contraseña. Las cuentas ya existentes conservan la suya. En una base configurada con `ENVIRONMENT=production` o `prod`, el seeder se bloquea por defecto. Para sembrar datos ficticios en producción, habilítalo de forma deliberada:

```powershell
python seed_demo_business.py --allow-production
```

Ese último comando agrega registros a la base indicada por `DATABASE_URL`; no es necesario para compilar ni iniciar el backend. No se ejecuta automáticamente durante el despliegue.

## Cuentas

- Empresa: `admin.<codigo>@example.test`
- Nutricionista: `nutritionist.<codigo>.<sucursal>@example.test`
- Paciente: `patient.<codigo>.<numero>@example.test`

El diario de comidas se asocia a cada paciente de muestra.

Los códigos de empresa son `vidasana`, `nutrifit`, `equilibrio`, `andina` y `vitalia`. El CLI informa cuántos registros nuevos creó y el total bruto simulado. Repetirlo con la misma contraseña no duplica información ni cambia contraseñas de cuentas existentes.
