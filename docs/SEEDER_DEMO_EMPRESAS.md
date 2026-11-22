# Seeder de empresas de demostración

Genera cinco empresas ficticias con actividad entre el 1 de enero y el 22 de noviembre de 2026. Es una tarea manual; el servidor API no carga estas cinco empresas al iniciar.

## Reglas de los datos

- Reutiliza `VIDASANA` si ya existe; crea las otras empresas solo si faltan.
- Usa los planes y precios que define `SubscriptionService.PLANS`: dos empresas Básico con 8 y 10 pacientes, dos Profesional con 32 y 45, y una Premium con 64.
- Asigna 1, 1, 2, 3 y 5 sucursales como tamaños de muestra. Los planes actuales no definen límites de sucursales.
- Registra once periodos sucesivos de 30 días por empresa: diez `REPLACED` y uno `ACTIVE`, que cubre noviembre. No crea órdenes, capturas ni comprobantes falsos de PayPal.
- Crea cuentas y nombres ficticios con correos `@example.test`, pacientes vinculados, citas completadas y cobros de consulta en efectivo al precio vigente de USD 5.
- Agrega ocho recetas generales de muestra a cada empresa cuyo plan incluya `Recetario & Macros` (Profesional y Premium). Son recetas de catálogo, sin prescripción individual ni asignaciones automáticas.
- Agrega uno o dos registros manuales de comidas por paciente y por mes activo. Son diarios auto-reportados sintéticos; no simulan análisis por foto ni respuestas de Gemini.
- Es idempotente: las claves estables evitan duplicados. Las empresas, sucursales y cuentas que ya existían no se borran ni se reemplazan.

No crea anamnesis, diagnósticos, ni planes nutricionales aprobados: la anamnesis requiere consentimiento y el plan real debe generarse con esos datos y pasar por revisión profesional. El catálogo base de alimentos y parámetros del sistema experto se carga por `prepare_db.py`.

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

Los códigos de empresa son `vidasana`, `nutrifit`, `equilibrio`, `andina` y `vitalia`. El CLI informa cuántos registros nuevos creó. Repetirlo con la misma contraseña no duplica información ni cambia contraseñas de cuentas existentes.
