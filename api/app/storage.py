###################################################################################################
# Blob storage - documents and audit packets, encrypted at rest with the PHI key.
#
# Files are written under STORAGE_PATH/<accountid>/<kind>/<recordid>.bin. The associated data is
# the storage key itself, so a blob renamed onto another record will not open. Swap this module
# for S3/Backblaze (with SSE and a BAA) without touching callers.
###################################################################################################
import hashlib
from pathlib import Path

from sqlalchemy.engine import Connection

from app import crypto, images
from app.config import settings
from app.db import newid, row, run


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def put(accountid: str, kind: str, recordid: str, data: bytes) -> str:
    return put_at(f"{accountid}/{kind}/{recordid}.bin", data)


def put_at(key: str, data: bytes) -> str:
    """Write at a key that is already recorded somewhere. The key is the associated data, so bytes
    written here open only under the key they were written for."""
    path = Path(settings.storage_path) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    version, blob = crypto.seal_bytes(data, key)
    path.write_bytes(version.to_bytes(2, "big") + blob)
    return key


def exists(key: str) -> bool:
    return (Path(settings.storage_path) / key).exists()


class Missing(Exception):
    """The row says there is a file, but the blob is not where it should be."""


# Where a document came from, and the only one of these the office may ever take back.
#
# Stamped by whoever stores the bytes, because that is the one moment it is known for certain.
# Anything else - and `uploadedby` was the obvious candidate - is reconstruction, and the
# reconstruction was wrong: of six documents that arrived through an upload link, one carried a
# user and five did not.
OFFICE, DRIVER, SERVICE, THIRDPARTY = "office", "driver", "service", "thirdparty"


def keep(conn: Connection, accountid: str, kind: str, data: bytes, filename: str,
         mimetype: str | None, userid: str | None = None, origin: str | None = None) -> str:
    """File these bytes for this account and answer with the document id.

    The same bytes are kept once: two drivers sending the same blank form, or one office filing the
    same scan against two things, share a row. But a row is only evidence that a file was stored -
    it is not the file. Where the blob behind an existing row has gone, these bytes are written to
    the key that row already carries, rather than the upload being silently dropped on the floor
    and the reader left with a document that cannot be opened."""
    # A photograph becomes a document before it is filed - see app/images.py. The hash is taken of
    # what is stored, not of what was sent, because the hash is how the file is found again.
    data, mimetype, filename = images.to_pdf(data, mimetype, filename)
    digest = sha256(data)
    held = row(conn, """
        SELECT recordid, storagekey FROM documents WHERE accountid = :a AND sha256 = :h
    """, a=accountid, h=digest)
    if held:
        if not exists(held["storagekey"]):
            put_at(held["storagekey"], data)
        # The same bytes are one row, so the origin already on it stands. That is the safe
        # direction: a file the driver sent does not become the office's because somebody in
        # the office later uploaded a copy of it.
        return held["recordid"]
    documentid = newid()
    key = put(accountid, kind, documentid, data)
    run(conn, """
        INSERT INTO documents (recordid, accountid, filename, mimetype, bytes, sha256,
                               storagekey, uploadedby, origin)
        VALUES (:id, :a, :f, :m, :b, :h, :k, :u, :o)
    """, id=documentid, a=accountid, f=(filename or "document")[:255],
        m=mimetype or "application/octet-stream", b=len(data), h=digest, k=key, u=userid,
        o=origin)
    return documentid


def get(key: str) -> bytes:
    path = Path(settings.storage_path) / key
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise Missing(key)
    return crypto.open_bytes(int.from_bytes(raw[:2], "big"), raw[2:], key)
