# Catálogo de recetas compartido — 23/11/2026

El seeder genera ocho recetas por empresa Profesional/Premium con `branch_id=NULL`.
El filtro ORM de sucursal las excluía incluso cuando pertenecían a la empresa del usuario.
La prueba `test_shared_recipe_catalog.py` reprodujo el fallo: devolvía solo la receta
local y omitía el catálogo compartido.

Se permite leer recetas sin sucursal de la misma empresa, además de las de la
sucursal seleccionada. Se mantienen los filtros de pacientes, asignaciones y
escrituras y la separación entre empresas.

Validación: pruebas del catálogo, seeder y recetas/clínica: 9 aprobadas.
Pruebas adicionales de aislamiento: 8 aprobadas y 3 fallidas. Las tres esperan
acceso global del superadmin a operaciones empresariales, que la política actual
bloquea con HTTP 403; requieren actualización al contrato del superadmin.
Para publicar se requiere desplegar solo backend; no cambia el esquema ni requiere
ejecutar nuevamente el seeder si las recetas ya están almacenadas.
La presencia de datos en Railway no se certificó: la conexión disponible no muestra
el proyecto NutriSalud.
