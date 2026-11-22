# Document email implementation plan

**Goal:** Enviar comprobantes, constancias, notas y reportes PDF/Excel al correo editable, inicialmente el de la cuenta.

**Architecture:** Un endpoint genera los mismos documentos autorizados que las descargas existentes y los adjunta por Brevo. Un formulario reutilizable en Angular y Flutter permite editar destinatario y elegir PDF/Excel para reportes. No modifica el correo de la cuenta.

**Tech Stack:** FastAPI, Brevo HTTP, Angular, Flutter.

## Tasks
- [ ] Backend: `app/api/v1/document_email.py`, `app/services/email_service.py`, router. Allowlist de descargas internas, permisos originales, email validado, adjuntos base64, errores reales de proveedor. Tests en `tests/test_document_email.py`: destinatario editado, permisos, PDF/Excel, fallo Brevo, rutas inválidas.
- [ ] Web: componente `shared/ui/email-document.component.ts` con correo editable, selección de formatos y estado de envío. Integrarlo junto a todas las descargas de citas, cobros, suscripciones, notas y reportes actuales/guardados. Compilar producción.
- [ ] Mobile: widget `widgets/email_document_button.dart`, integrarlo en citas, recibos de pagos/recargas/suscripción y reportes. Analizar, probar y regenerar APK.
- [ ] Publicar los tres repositorios y verificar endpoints y bundles desplegados. No enviar correos de prueba a terceros sin destinatario indicado.

## Review focus
- El correo editado solo afecta este envío.
- Ningún documento de otra empresa/paciente puede enviarse.
- Reportes usan los mismos filtros, atributos y rangos que la descarga.
- Un fallo de Brevo nunca se muestra como envío correcto.
- PDF y Excel se envían juntos o por separado según selección.
