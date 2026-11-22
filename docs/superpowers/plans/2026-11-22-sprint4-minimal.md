# Sprint 4 minimal implementation plan

**Goal:** Completar CU-19 a CU-24 reutilizando clínica, planes, vínculos, administración y consola existentes.

**Architecture:** API `/care` con mediciones históricas, evaluaciones de adherencia con parámetros conservados, revisión profesional, mensajes y lotes CSV. Componentes web y pantalla móvil consumen la misma API. La consola `/platform` amplía filtros, fecha e incidencias sin datos clínicos.

**Tech Stack:** FastAPI/SQLAlchemy/Alembic, Angular 22, Flutter.

**Spec:** CU-19 a CU-24 del documento Google del proyecto, revisados en `diagramas_sprint4/prompts_tiempo` del workspace.

## Global constraints
- Reutilizar roles y aislamiento de empresa/vínculo. Superadmin exclusivamente comercial/operativo.
- Modelo mínimo; CSV como único formato de importación con plantilla y confirmación.
- Adherencia inicial = registro de comidas frente a la cantidad del plan, por día; explicar que no mide cumplimiento de composición nutricional.
- Históricos sin datos inventados. Nuevas mediciones se conservan; no reconstruir mediciones antiguas desde valores actuales.
- Publicar backend/web/mobile y generar APK después de pruebas. Preservar cambios locales ajenos.

## Tasks
- [ ] Modelos y migración: Measurement, NutritionConfiguration, CareAssessment, PlanReview, CareMessage, PatientImportBatch y PlatformIncident.
- [ ] CU-19/22: mediciones, período acotado, plan vigente, datos faltantes, alerta deduplicada y parámetros versionados por empresa. Pruebas de fórmula, fechas, permisos y snapshots.
- [ ] CU-20: corrección, aprobación/rechazo con motivo e historial; conservar mecanismo de aprobación actual. Pruebas de permisos, estados y auditoría.
- [ ] CU-21: conversaciones solo entre participantes vinculados, historial paginado y notificación; error visible en clientes. Pruebas de aislamiento y vínculo.
- [ ] CU-23: CSV validado por fila, previsualización sin altas, token de lote con caducidad, confirmación única y resumen. Reutilizar validación de cuentas/cupo/sucursal; nunca devolver contraseñas. Pruebas de duplicados, errores, confirmación y reintento.
- [ ] CU-24: filtro por empresa/período con definición explícita de métricas, fecha de actualización y registro saneado de incidencias 500. Pruebas de acceso root y datos excluidos.
- [ ] Web: panel compacto reutilizable con cinco apartados; paciente solo progreso y mensajes. Importación accesible con plantilla CSV. Ampliar consola root.
- [ ] Mobile: pantalla de seguimiento propio, mediciones y conversación, accesible desde Perfil. Análisis y pruebas, APK.
- [ ] Verificación de migración, pruebas focalizadas, build web, análisis/tests Flutter; commits explícitos y despliegues verificados.

## Review focus
- Datos ajenos, pacientes sin vínculo y empresa suspendida deben quedar bloqueados.
- Ausencia de comidas no equivale a cumplimiento; comidas de un día no compensan otro.
- Cambios de configuración no reinterpretan evaluaciones guardadas.
- CSV inválido o cancelado no crea usuarios; confirmaciones repetidas no duplican.
- No mostrar contenido clínico, contraseñas ni mensajes en incidencias de plataforma.
