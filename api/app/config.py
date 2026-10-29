###################################################################################################
# Settings - read from the environment (or api/.env). Nothing secret has a usable default: the app
# refuses to start without a JWT secret and a PHI key.
###################################################################################################
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "DBServer"
    db_port: int = 3306
    db_user: str = "tripproof"
    db_password: str = ""
    db_name: str = "tripproof"

    # HS256 signing secret for access tokens.
    jwt_secret: str
    # How long a sign-in lasts without being renewed. The office app renews it every few minutes
    # while somebody is using it, so this is the idle limit, not the length of a working day: a
    # session ends after this long with nobody at the keyboard, never while they are working.
    jwt_minutes: int = 60

    # PHI keys: "version:base64key" pairs, comma separated. The highest version seals new data;
    # every listed version can still open old data, which is how keys are rotated.
    # Generate one with: python -c "import os,base64;print('1:'+base64.b64encode(os.urandom(32)).decode())"
    phi_keys: str

    # Where encrypted document and packet blobs are written.
    storage_path: str = "/data/storage"

    cors_origins: str = "http://localhost:5173"

    # Where people reach the web app; invitation links point here.
    public_url: str = "http://localhost:8080"

    # Outgoing mail for invitations. With no SMTP_HOST, nothing is sent and the admin portal shows
    # the invitation link to copy instead (fine for development, not for production).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Trip Proof Online <noreply@tripproofonline.com>"
    smtp_starttls: bool = True       # port 587: upgrade to TLS after connecting
    smtp_insecure: bool = False      # development only: skip the mail server's certificate check
    smtp_ssl: bool = False           # port 465: TLS from the first byte

    # Stripe, for the online application's card verification and the customer record. Leave both
    # empty in development: /apply then lets the card step be skipped.
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    # MapTiler, for the dashboard map. Public by necessity - a map style URL is fetched by
    # the browser - so it is restricted at MapTiler by origin rather than kept secret here.
    # Empty means the map falls back to OpenStreetMap raster tiles, which need no key.
    maptiler_key: str = ""
    # Signing secret of the webhook endpoint (whsec_…) - from the Stripe dashboard's endpoint, or
    # printed by `stripe listen` in development. Without it the webhook refuses every event.
    stripe_webhook_secret: str = ""
    # backgroundchecks.com, for background screening. Absent, the ordering is simply off and the
    # requirement falls back to a report filed by hand.
    # The base url is the SANDBOX by default: an installation that has not been told which world it
    # is in must not be ordering real reports against a real invoice.
    backgroundchecks_api_token: str = ""
    backgroundchecks_base_url: str = "https://sandbox.backgroundchecks.com/api"
    # What a webhook from them has to present before it is believed. Absent, webhooks are refused
    # outright - an open endpoint that files background screenings is not a thing to leave ajar.
    backgroundchecks_webhook_key: str = ""
    # The platform credentials, for the Connect widgets. The source token identifies this product
    # to their registration widget; the private key is what turns the token that widget hands back
    # into one company's own API key. Absent, the widgets are simply not offered.
    backgroundchecks_source_token: str = ""
    backgroundchecks_private_key: str = ""
    # MapTiler. Two keys, deliberately:
    #   maptiler_key          goes to the BROWSER for tiles, so it is readable by anyone who
    #                         views the page - which is why it is locked to our own origin in
    #                         the MapTiler account, and must stay locked.
    #   maptiler_server_key   is used only from here, for geocoding. A server sends no Referer,
    #                         so an origin-locked key is refused 403; this one carries no origin
    #                         restriction and therefore must never reach a browser.
    # Absent, geocoding falls back to the browser key and then to OpenStreetMap.
    maptiler_server_key: str = ""
    # Texts to drivers (app/sms.py). No account SID: nothing is sent, and each text is kept as "off".
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from: str = ""             # the number texts come from, +1XXXXXXXXXX
    # Where routes are worked out (app/routing.py): an OSRM server. Empty means the public one.
    osrm_url: str = ""
    # Certn, the screening vendor before them. Kept so orders placed through Certn can still be
    # read and still land; nothing new is ordered there.
    certn_api_key: str = ""
    certn_base_url: str = "https://api.certn.co"
    certn_webhook_secret: str = ""


settings = Settings()
