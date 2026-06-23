from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies.roles import require_admin
from app.models.user import User
from app.schemas.admin import AdminDashboardOut
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard", response_model=AdminDashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return AdminService(db).get_dashboard()
