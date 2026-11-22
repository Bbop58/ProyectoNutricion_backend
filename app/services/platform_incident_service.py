import logging
from app.models.care import PlatformIncident


def record_incident(request,exc):
    """Store route templates and error class only, never payloads or patient IDs."""
    from app.database import get_session_local
    try:
        route=getattr(request.scope.get('route'),'path','unknown')
        with get_session_local()() as db:
            db.add(PlatformIncident(method=request.method[:10],route=route[:200],error_type=type(exc).__name__[:100]))
            db.commit()
    except Exception:
        logging.getLogger('api').warning('Could not persist platform incident metadata')
