###################################################################################################
# Signatures - one adopted signature per signer, reused to sign every document.
#
# Three kinds of signer:
#   driver       an applicant or working driver; proves identity with date of birth + SSN
#   user         someone who signs on behalf of the account; proves it the same way, from inside
#                their own session, so the signature is tied to a real login
#   thirdparty   a medical examiner, a previous employer, anyone outside the account; reached by a
#                link, so there is no DOB/SSN to check and `verifiedby` says 'link'
#
# Adopting a signature records what was typed and which face it is drawn in. Signing a document
# records the SHA-256 of the exact text shown at the moment of signing, so the record can be proved
# later even if the wording of that document changes.
###################################################################################################
import hashlib
import hmac
import re

# THE signature faces, by the key the driver chose. One map, because two copies of it is exactly
# how one person's signature came to be drawn in two different hands on two forms they signed in
# the same sitting. The keys are the ones the signing dialog offers; changing one here changes it
# everywhere a signature is drawn.
SIGNATURE_FONTS = {"signature": "meddon.ttf",
                   "quick": "kristi.ttf",
                   "hand": "zeyada.ttf",
                   "cursive": "cedarville-cursive.ttf",
                   "modern": "ms-madi.ttf",
                   "fine": "herr-von-muellerhoff.ttf",
                   "bold": "style-script.ttf",
                   "alexbrush": "alex-brush.ttf",
                   "birthstone": "birthstone.ttf",
                   "dancing": "dancing-script.ttf",
                   "ephesis": "ephesis.ttf",
                   "greatvibes": "great-vibes.ttf",
                   "kalam": "kalam.ttf",
                   "marck": "marck-script.ttf",
                   "montecarlo": "monte-carlo.ttf",
                   "satisfy": "satisfy.ttf",
                   "whisper": "whisper.ttf"}


from sqlalchemy.engine import Connection

from app import crypto
from app.db import newid, row, rows, run

# The hands a signature can be drawn in, the default first. The key is what gets stored, so a
# rendered signature looks the same everywhere it is shown: the stylesheet knows these as .font-*
# (web/src/styles.css, web/src/lib/signatureFonts.js) and the PDF writer as SIGNATURE_FONTS.
# Offered (and accepted) for a new signature; the earlier seven in SIGNATURE_FONTS stay only so the
# signatures already made in them are drawn as they were signed.
FONTS = ("alexbrush", "birthstone", "dancing", "ephesis", "greatvibes", "kalam", "marck", "montecarlo", "satisfy", "whisper")

DOC_TYPES = {
    "I9": "Form I-9, Employment Eligibility Verification",
    # The office's half of the same form: somebody examined the employee's documents and
    # certified Section 2. Filed against the DRIVER, like Section 1 - an I-9 is the driver's
    # document - and under its own doctype so the two signatures stay apart.
    "I9_SECTION2": "Form I-9, Section 2 employer certification",
    "W4": "Form W-4, Employee's Withholding Certificate",
    "FCRA_SUMMARY": "A Summary of Your Rights Under the Fair Credit Reporting Act",
    "FCRA_AUTH": "Background check disclosure and authorization",
    "WORKPLACE_POLICY": "Workplace policy acknowledgement",
    "DRUG_POLICY": "Drug and alcohol policy acknowledgement",
    "PHI_ACK": "PHI confidentiality and privacy acknowledgment",
    "CLEARINGHOUSE_CONSENT": "FMCSA Clearinghouse query consent",
    "SAFETY_PERFORMANCE_CONSENT": "Consent to release safety performance history",
    "APPLICATION": "Driver application certification",
    "ANNUAL_REVIEW": "Annual review of driving record",
    "PREEMP_DA_QUESTIONNAIRE": "Pre-employment drug and alcohol questionnaire, 49 CFR 40.25(j)",
    # Whether a license has been revoked, suspended or denied in the last three years: the driver's
    # own signed answer, which decides whether Florida's license-status notice reaches them.
    "LICENSE_ACTION_QUESTION": "License revocation, suspension or denial statement",
    # A form the driver fills in rather than a document they are handed: what is signed is their
    # own figures - the hours they had already worked before they got here, 49 CFR 395.8(j)(2).
    "PREV7_ONDUTY": "Previous 7 Days' On-Duty Hours Statement",
    # Signed by a user of the account rather than by a driver - the supervisor themselves,
    # acknowledging the training that lets them send somebody for a reasonable suspicion test.
    # 49 CFR 382.603.
    "SUPERVISOR_TRAINING_RECORD": "Reasonable suspicion supervisor training record",
    "BBP_EXPOSURE_DETERMINATION": "Bloodborne pathogens occupational exposure determination",
}


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def ssn_hash(accountid: str, ssn: str) -> str:
    """A lookup value for an SSN. HMAC under the current PHI key, scoped to one account, so the
    same person applying to two accounts does not link across them, and the stored value cannot be
    reversed to the number."""
    key = crypto._KEYS[crypto.CURRENT_VERSION]
    return hmac.new(key, f"{accountid}:{digits(ssn)}".encode(), hashlib.sha256).hexdigest()


def valid_ssn(ssn: str) -> bool:
    d = digits(ssn)
    if len(d) != 9 or d == "0" * 9:
        return False
    area, group, serial = d[:3], d[3:5], d[5:]
    return area not in ("000", "666") and not area.startswith("9") and group != "00" and serial != "0000"


def _platform_hash(ssn: str, version: int) -> str:
    """The SSN's lookup value across every company - the one place a number is compared outside the
    account it was given to, and only to keep one number to one person."""
    return hmac.new(crypto._KEYS[version], f"platform:{digits(ssn)}".encode(), hashlib.sha256).hexdigest()


def _same_name(a: str | None, b: str | None) -> bool:
    return " ".join((a or "").upper().split()) == " ".join((b or "").upper().split())


TAKEN = ("This Social Security number is already used for another signature. "
         "A signature can only be created for a number that is not already on file.")


def claim(conn: Connection, accountid: str, signertype: str, signerid: str, signername: str,
          ssn: str, dob) -> None:
    """Register this SSN to this signer, or refuse.

    One number is one person, on every company. It is accepted when it is not registered yet, when
    this signer already holds it, or when the same person - same company, same date of birth, same
    name - is signing as the other of office user and driver. Anything else is refused, whatever
    date of birth comes with it: a number typed with a birth date that is not its owner's is
    exactly the case this exists to stop."""
    if not valid_ssn(ssn):
        raise ValueError("That Social Security number doesn't look right")
    # Under every key there has been, so a number registered before a key rotation is still found.
    held = [r for v in crypto._KEYS for r in rows(
        conn, "SELECT recordid, dob, fullname FROM signatureidentities WHERE ssnhash = :h",
        h=_platform_hash(ssn, v))]
    mine = row(conn, """
        SELECT identityid FROM signatureidentitysigners
        WHERE accountid = :a AND signertype = :t AND signerid = :s
    """, a=accountid, t=signertype, s=signerid)
    if not held:
        if mine:
            # This signer is already somebody else on file and is now giving a different number.
            raise ValueError(TAKEN)
        identityid = newid()
        run(conn, """
            INSERT INTO signatureidentities (recordid, ssnhash, keyversion, dob, fullname)
            VALUES (:id, :h, :v, :d, :n)
        """, id=identityid, h=_platform_hash(ssn, crypto.CURRENT_VERSION), v=crypto.CURRENT_VERSION,
            d=dob, n=" ".join((signername or "").upper().split())[:128])
    else:
        identity = held[0]
        identityid = identity["recordid"]
        if mine and mine["identityid"] == identityid:
            return
        signers = rows(conn, "SELECT accountid, signertype FROM signatureidentitysigners "
                             "WHERE identityid = :i", i=identityid)
        alike = (not mine and identity["dob"] == dob and _same_name(identity["fullname"], signername)
                 and all(s["accountid"] == accountid and s["signertype"] != signertype
                         and s["signertype"] in ("user", "driver") for s in signers))
        if not alike:
            raise ValueError(TAKEN)
    run(conn, """
        INSERT INTO signatureidentitysigners (identityid, accountid, signertype, signerid)
        VALUES (:i, :a, :t, :s)
    """, i=identityid, a=accountid, t=signertype, s=signerid)


def recognise(conn: Connection, accountid: str, signertype: str, signerid: str, signername: str,
              ssn: str, dob) -> None:
    """Register a signer who already had a signature before the register existed, the next time they
    prove their date of birth and SSN - the one moment the number is in hand to register. A signer
    with no signature yet is left to `adopt`, which claims the number when it creates one."""
    if current(conn, accountid, signertype, signerid):
        claim(conn, accountid, signertype, signerid, signername, ssn, dob)


def adopt(conn: Connection, accountid: str, signertype: str, signerid: str | None, signername: str,
          typedname: str, fontkey: str, verifiedby: str, ip: str | None = None, useragent: str | None = None,
          email: str | None = None, role: str | None = None, *, ssn: str | None = None,
          dob=None) -> dict:
    """Record an adopted signature. Any earlier one for the same signer is revoked, so there is
    exactly one signature in force and older signings still point at the one that made them.

    A driver's or office user's signature is created only once their SSN is claimed for them - see
    `claim`. A third party signs by link and has no number to claim."""
    if signertype not in ("driver", "user", "thirdparty"):
        raise ValueError("Unknown signer type")
    if signertype in ("driver", "user"):
        if not ssn or not dob or not signerid:
            raise ValueError("A signature needs the signer's date of birth and Social Security number")
        claim(conn, accountid, signertype, signerid, signername, ssn, dob)
    typedname = " ".join((typedname or "").split())
    if len(typedname) < 2:
        raise ValueError("Type your name as your signature")
    if fontkey not in FONTS:
        fontkey = FONTS[0]
    if signerid:
        run(conn, """
            UPDATE signatures SET revokedon = UTC_TIMESTAMP()
            WHERE accountid = :a AND signertype = :t AND signerid = :s AND revokedon IS NULL
        """, a=accountid, t=signertype, s=signerid)
    sigid = newid()
    run(conn, """
        INSERT INTO signatures (recordid, accountid, signertype, signerid, signername, typedname, fontkey,
                                email, role, verifiedby, ip, useragent)
        VALUES (:id, :a, :t, :s, :n, :tn, :f, :e, :r, :v, :ip, :ua)
    """, id=sigid, a=accountid, t=signertype, s=signerid, n=signername[:128], tn=typedname[:128], f=fontkey,
        e=email, r=role, v=verifiedby, ip=ip, ua=(useragent or "")[:255] or None)
    return current(conn, accountid, signertype, signerid) or {"recordid": sigid}


def current(conn: Connection, accountid: str, signertype: str, signerid: str | None) -> dict | None:
    return row(conn, """
        SELECT recordid, signername, typedname, fontkey, verifiedby, ip, createdon
        FROM signatures
        WHERE accountid = :a AND signertype = :t AND signerid = :s AND revokedon IS NULL
        ORDER BY createdon DESC LIMIT 1
    """, a=accountid, t=signertype, s=signerid)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def sign(conn: Connection, accountid: str, signatureid: str, doctype: str, ownerid: str, content: str,
         ownertype: str = "driver", version: str | None = None, ip: str | None = None,
         useragent: str | None = None, contenthash: str | None = None,
         recordid: str | None = None, signedon=None) -> str:
    """`contenthash` is for a document the server holds as a file rather than as text - the
    company's own policy, whose SHA-256 is already recorded against the stored file.

    THE WORDS ARE KEPT, not only their hash. A policy fills itself in from live data - the
    company's name, its effective date, the DER from the appointment on file - so the copy it
    renders today is not the copy somebody signed in March. The hash proves the words were not
    altered; it cannot reproduce them. Appoint a new DER in June and every signed acknowledgment
    would otherwise print the new name over an old signature, which is worse than printing nothing.
    So the filled text is stored with the signature and read back from there.
    """
    if doctype not in DOC_TYPES:
        raise ValueError(f"Unknown document type {doctype}")
    # A document that carries its own audit stamp is drawn before it is recorded, so the caller can
    # hand in the id and the moment it will be signed at and have the two agree.
    recordid = recordid or newid()
    run(conn, """
        INSERT INTO documentsignatures (recordid, accountid, signatureid, doctype, ownertype, ownerid,
                                        contentsha256, contentversion, signedtext, ip, useragent,
                                        signedon)
        VALUES (:id, :a, :sig, :d, :ot, :oid, :h, :v, :text, :ip, :ua, COALESCE(:on, UTC_TIMESTAMP()))
        ON DUPLICATE KEY UPDATE contentsha256 = VALUES(contentsha256), contentversion = VALUES(contentversion),
                                signedtext = VALUES(signedtext),
                                signedon = VALUES(signedon), ip = VALUES(ip), useragent = VALUES(useragent)
    """, id=recordid, a=accountid, sig=signatureid, d=doctype, ot=ownertype, oid=ownerid,
        h=contenthash or content_hash(content), v=version,
        # Only where the words are what was signed. A document the server holds as a FILE is
        # reproduced from the file itself, and keeping a second copy of it here would give one
        # document two originals.
        text=(content if content and not contenthash else None),
        ip=ip, ua=(useragent or "")[:255] or None, on=signedon)
    return recordid


def signed(conn: Connection, accountid: str, ownerid: str, ownertype: str = "driver") -> dict[str, dict]:
    return {r["doctype"]: r for r in rows(conn, """
        SELECT d.recordid, d.doctype, d.signedon, d.contentsha256, d.contentversion, d.ip,
               d.signedtext,
               -- The signature on file that was used, which is what an audit stamp names -
               -- the same id the signature box shows on screen.
               s.recordid AS signatureid,
               s.typedname, s.fontkey, s.signername, s.signertype
        FROM documentsignatures d JOIN signatures s ON s.recordid = d.signatureid
        WHERE d.accountid = :a AND d.ownertype = :ot AND d.ownerid = :oid
    """, a=accountid, ot=ownertype, oid=ownerid)}
