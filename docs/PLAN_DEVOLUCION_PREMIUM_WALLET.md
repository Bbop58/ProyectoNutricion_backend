# Devolución total de Premium IA a wallet

**Regla acordada:** devolver todo lo pagado, una sola vez por suscripción personal.
El saldo es crédito interno USD para consultas, no dinero devuelto a PayPal.
El superadmin decide porque el Premium IA pertenece a la plataforma. No accede a
fichas clínicas, comidas ni citas para resolver la solicitud.

## Flujo y estados

Cliente con pago confirmado y Premium vigente → solicitud PENDING con motivo →
superadmin APPROVED o REJECTED con motivo. Mientras está pendiente mantiene
Premium. Aprobar acredita el importe histórico pagado y marca la suscripción
REFUNDED en una transacción. Rechazar no cambia acceso ni wallet.

Solo CLIENTE_PREMIUM, moneda USD, importe positivo y recibo PayPal consistente
con el comprador y la captura guardada. Se permiten pagos Sandbox reales de
prueba, pero nunca referencias DEMO-* ni asignaciones manuales sin cobro.
No admite períodos vencidos/reemplazados/cancelados ni importes del dispositivo.

## Implementación

- [x] Tabla subscription_wallet_refunds: solicitud y decisión, importe histórico,
  comprador, captura única, suscripción única y movimiento/operación vinculados.
- [x] Migración aditiva, respaldo y restauración compatibles. Los reembolsos y la
  wallet son registros financieros de plataforma; no se exportan/restauran desde
  el respaldo operativo de una empresa. La restauración no puede acreditar saldo.
- [x] Backend con bloqueos de fila, restricciones únicas, respuesta idempotente,
  auditoría y comprobante PDF. El crédito queda fuera de ingresos de caja.
- [x] Móvil: solicitud online desde el comprobante, confirmación de importe total,
  estado, motivo de rechazo, refresco, PDF y saldo visible en la wallet existente.
- [x] Web superadmin: lista paginada, aprobar/rechazar con motivo obligatorio y
  protección frente a doble clic. Mostrar que se cierra el Premium.
- [x] Pruebas: propietario/roles, demo, importe, vencimiento, rechazo, repetición,
  atomicidad, aislamiento, PDF y conciliación de saldo y caja.
- [ ] Publicar backend y web, generar APK apuntando a Railway y entregar artefacto.

Las pruebas de mutaciones y abonos se ejecutan exclusivamente en bases aisladas.
La comprobación remota será de salud y rutas/permisos, sin créditos ficticios
ni reembolsos a cuentas existentes para probar la implementación.

Validación local: suite de 50 pruebas backend de wallet, suscripciones, consola y
migraciones aprobada; después, 19 pruebas específicas finales de devolución
aprobadas (incluyen consulta a PayPal simulada, caída de proveedor y pago ya
reembolsado). Son conjuntos superpuestos, no 69 pruebas distintas. Web: 5 pruebas
y build de producción/PWA aprobados. Móvil: 22 pruebas anteriores/flujo nuevo
aprobadas y 2 pruebas finales de devolución aprobadas tras corregir el caso de
fallo de red. Análisis Dart dirigido sin incidencias. Las pruebas del proveedor
usan dobles; no se realizó un abono remoto ni una carrera real en PostgreSQL.
