-- ################################################################################################
-- # 404 - the facility portal. A dialysis centre, clinic or hospital on the company's Locations list
-- # gets logins of its own: to request trips to and from it, see them, press Ready For Pickup on a
-- # will-call return, and cancel. Requests wait for the office; nothing a facility sends is a trip
-- # until a dispatcher accepts it.
-- ################################################################################################

-- Whether this place may use the portal, and the payer its contracted trips are billed to (a
-- company payer, usually a flat contract). No contract: the facility's trips are private pay.
ALTER TABLE places ADD COLUMN IF NOT EXISTS portal TINYINT(1) NOT NULL DEFAULT 0 AFTER closesat;
ALTER TABLE places ADD COLUMN IF NOT EXISTS contractpayerid VARCHAR(36) NULL AFTER portal;

-- The facility's own logins. Several per place; each person their own.
CREATE TABLE IF NOT EXISTS facilityusers (
  recordid      VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid     VARCHAR(36)  NOT NULL,
  placeid       VARCHAR(36)  NOT NULL,
  name          VARCHAR(120) NOT NULL,
  email         VARCHAR(255) NOT NULL,
  passwordhash  VARCHAR(255) NULL,
  passwordseton DATETIME     NULL,
  sessionid     VARCHAR(36)  NULL,
  lastloginon   DATETIME     NULL,
  closedon      DATETIME     NULL,
  added         DATETIME     NOT NULL,
  addedby       VARCHAR(36)  NULL,
  KEY ix_facilityusers_place (accountid, placeid),
  KEY ix_facilityusers_email (email)
);

-- Invitation and reset links for them, beside the office users' and drivers'.
ALTER TABLE passwordtokens ADD COLUMN IF NOT EXISTS facilityuserid VARCHAR(36) NULL AFTER driverid;
ALTER TABLE passwordtokens DROP CONSTRAINT IF EXISTS ck_passwordtokens_subject;
ALTER TABLE passwordtokens ADD CONSTRAINT ck_passwordtokens_subject CHECK (
  (userid IS NOT NULL) + (driverid IS NOT NULL) + (facilityuserid IS NOT NULL) = 1);

-- A trip a facility asked for. `body` is the booking exactly as it will be made; accepting it
-- books it through the same checks as any other booking and links the trip here.
CREATE TABLE IF NOT EXISTS triprequests (
  recordid       VARCHAR(36)  NOT NULL PRIMARY KEY,
  accountid      VARCHAR(36)  NOT NULL,
  placeid        VARCHAR(36)  NOT NULL,
  facilityuserid VARCHAR(36)  NOT NULL,
  state          VARCHAR(10)  NOT NULL DEFAULT 'requested',   -- requested | accepted | declined | withdrawn
  passenger      VARCHAR(160) NOT NULL,
  tripdate       DATE         NOT NULL,
  pickupat       DATETIME     NOT NULL,                       -- the first pickup, for sorting and the board
  body           LONGTEXT     NOT NULL,
  requestedon    DATETIME     NOT NULL,
  decidedon      DATETIME     NULL,
  decidedby      VARCHAR(36)  NULL,
  declinereason  VARCHAR(400) NULL,
  tripid         VARCHAR(36)  NULL,
  KEY ix_triprequests_open (accountid, state, tripdate),
  KEY ix_triprequests_place (accountid, placeid, tripdate)
);
