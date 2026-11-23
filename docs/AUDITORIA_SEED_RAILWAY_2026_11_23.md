# Revisión del seeder en Railway — 23/11/2026

Se consultó la API desplegada de NutriSalud con las cinco cuentas demo de empresa,
recorriendo las doce sucursales mediante cabeceras de ámbito, sin cambiar su
selección persistente. El conector OAuth de Railway no expone credenciales ni SQL;
esta evidencia valida los datos visibles por API, no una auditoría SQL integral.

| Empresa | Sucursales | Pacientes del seeder | Citas y cobros | Recetas únicas |
| --- | ---: | ---: | ---: | ---: |
| Vida Sana | 1 | 8 | 16 | 0 |
| NutriFit | 1 | 10 | 21 | 0 |
| Equilibrio | 2 | 32 | 70 | 8 |
| Andina | 3 | 45 | 101 | 8 |
| Vitalia | 5 | 64 | 144 | 8 |

Cada empresa tiene once periodos del seeder y sus once recibos. Cobros de consulta:
USD 1.760; recibos de suscripción: USD 1.319,45. Los datos son sintéticos.
Las recetas compartidas se ven en todas las sucursales correspondientes después
del despliegue 118c36d. Vida Sana tiene además dos pacientes ajenos al seeder;
no se eliminaron ni se contaron como pacientes generados por él.

Se encontró un fallo: `/subscriptions/current` devolvía CLIENTE_PREMIUM para
Vida Sana. El plan personal antiguo de un paciente conservaba tenant_id y resultaba
más reciente que el plan BASICO de la empresa. La consulta de suscripción activa
por empresa ahora excluye planes CLIENTE_, conservando su consulta individual.
No se borraron suscripciones, cobros ni cuentas.

Prueba de regresión: falla antes del filtro y pasa con él; suite de consola y
recibos: 11 aprobadas. Las pruebas adicionales del seeder y recetario compartido
también pasaron durante la revisión (6 pruebas).

La revisión no certifica pagos reales de PayPal, utilidad neta, ni integridad
de todas las tablas mediante SQL.
