###################################################################################################
# Audits - requests from brokers/state, and the packets generated to answer them.
###################################################################################################
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import packets, storage
from app.activity import log
from app.db import get_conn, newid, row, rows, run, utcnow
from app.security import client_ip, current_user, editor

router = APIRouter(prefix="/api", tags=["audits"])


class AuditIn(BaseModel):
    requester: str
    reference: str | None = None
    receivedon: date
    dueon: date | None = None
    notes: str | None = None


class AuditPatch(BaseModel):
    status: str


@router.get("/audits")
def list_audits(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return rows(conn, """
        SELECT a.*, (SELECT COUNT(*) FROM auditpackets p WHERE p.auditrequestid = a.recordid) AS packets
        FROM auditrequests a WHERE a.accountid = :a ORDER BY a.receivedon DESC
    """, a=user["accountid"])


@router.post("/audits")
def create_audit(body: AuditIn, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    aid = newid()
    run(conn, """
        INSERT INTO auditrequests (recordid, accountid, requester, reference, receivedon, dueon, notes, createdby)
        VALUES (:id, :a, :req, :ref, :rec, :due, :notes, :u)
    """, id=aid, a=user["accountid"], req=body.requester, ref=body.reference, rec=body.receivedon, due=body.dueon,
        notes=body.notes, u=user["recordid"])
    log(conn, user, "create", "auditrequest", aid)
    return {"recordid": aid}


@router.patch("/audits/{auditid}")
def patch_audit(auditid: str, body: AuditPatch, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    if body.status not in ("open", "submitted", "closed"):
        raise HTTPException(400, "Unknown status")
    r = run(conn, "UPDATE auditrequests SET status = :s, updated = :now WHERE recordid = :id AND accountid = :a",
            s=body.status, now=utcnow(), id=auditid, a=user["accountid"])
    if not r.rowcount:
        raise HTTPException(404, "Audit not found")
    log(conn, user, "update", "auditrequest", auditid, {"status": body.status})
    return {"ok": True}


@router.get("/audits/{auditid}")
def get_audit(auditid: str, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    a = row(conn, "SELECT * FROM auditrequests WHERE recordid = :id AND accountid = :acct", id=auditid, acct=user["accountid"])
    if not a:
        raise HTTPException(404, "Audit not found")
    a["packets"] = rows(conn, """
        SELECT p.recordid, p.tripcount, p.sha256, p.bytes, p.added, p.runid, u.name AS generatedby
        FROM auditpackets p LEFT JOIN users u ON u.recordid = p.generatedby
        WHERE p.auditrequestid = :id ORDER BY p.added DESC
    """, id=auditid)
    return a


class PacketIn(BaseModel):
    # Trip numbers as the auditor listed them: separated by commas, spaces or new lines. A range
    # "1001-1100" expands when both ends are numbers of the same width.
    trips: str
    auditrequestid: str | None = None


def _expand(spec: str) -> list[str]:
    out: list[str] = []
    for token in re.split(r"[\s,;]+", spec.strip()):
        if not token:
            continue
        m = re.fullmatch(r"([A-Za-z]*)(\d+)-\1?(\d+)", token)
        if m and len(m.group(2)) == len(m.group(3)) and int(m.group(3)) >= int(m.group(2)):
            lo, hi, width = int(m.group(2)), int(m.group(3)), len(m.group(2))
            if hi - lo > 5000:
                raise HTTPException(400, f"Range {token} is larger than 5,000 trips")
            out.extend(f"{m.group(1)}{n:0{width}d}" for n in range(lo, hi + 1))
        else:
            out.append(token)
    return list(dict.fromkeys(out))


@router.post("/packets")
def create_packet(body: PacketIn, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    ids = _expand(body.trips)
    if not ids:
        raise HTTPException(400, "List at least one trip number")
    result = packets.build(conn, user, ids, body.auditrequestid)
    if "error" in result:
        raise HTTPException(404, result["error"])
    log(conn, user, "export", "auditpacket", result["recordid"], {"trips": result["tripcount"], "sha256": result["sha256"]},
        phi=True, ip=client_ip(request))
    return result


@router.get("/packets")
def list_packets(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    return rows(conn, """
        SELECT p.recordid, p.auditrequestid, a.requester, a.reference, p.tripcount, p.sha256, p.bytes, p.added
        FROM auditpackets p LEFT JOIN auditrequests a ON a.recordid = p.auditrequestid
        WHERE p.accountid = :a ORDER BY p.added DESC LIMIT 100
    """, a=user["accountid"])


@router.get("/packets/{packetid}/download")
def download_packet(packetid: str, request: Request, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    p = row(conn, "SELECT storagekey, added FROM auditpackets WHERE recordid = :id AND accountid = :a",
            id=packetid, a=user["accountid"])
    if not p:
        raise HTTPException(404, "Packet not found")
    log(conn, user, "download", "auditpacket", packetid, phi=True, ip=client_ip(request))
    name = f"tripproof-packet-{p['added']:%Y%m%d-%H%M}.zip"
    return Response(storage.get(p["storagekey"]), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
