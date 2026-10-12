from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from app.db import get_conn, rows
from app.security import current_user

router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/brokers")
def brokers(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return rows(conn, "SELECT recordid, code, name FROM payers "
                      "WHERE category = 'broker' ORDER BY name")
