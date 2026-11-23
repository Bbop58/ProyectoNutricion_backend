# Administrador de empresa con capacidades clínicas

Objetivo: conservar la administración de empresa y habilitar las capacidades de
nutricionista que faltaban: conversación directa con pacientes y atención de citas.

- [x] Añadir pruebas de contacto y conversación bidireccional admin/paciente,
  aislamiento de empresa/sucursal y agenda del administrador.
- [x] Habilitar contactos administrativos para pacientes de la misma empresa.
  El administrador usa la sucursal activa; los hilos siguen siendo entre sus
  participantes y no se abren conversaciones privadas de terceros.
- [x] Admitir ADMIN_ORGANIZATION como profesional en la agenda.
- [x] Mostrar Mensajes al administrador en Angular y cubrirlo con una prueba.
- [ ] Ejecutar pruebas de acceso, clínica, agenda y mensajería, compilar Angular,
  publicar backend/web y comprobar despliegues y contactos por API.

La app Flutter ya muestra Mensajes a administradores y obtiene contactos de la API;
no requiere modificar código ni regenerar APK para este cambio de permisos.
Las funciones de plataforma siguen reservadas al superadmin.

Validación local: 26 pruebas backend (seguimiento, mensajería, importación, consola,
aislamiento, recetas y clínica) aprobadas; 4 pruebas del componente Angular
aprobadas. Se preserva el vínculo al nutricionista y el acceso a hilos requiere
ser uno de los participantes autorizados.
