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
    jwt_minutes: int = 480

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
    # Certn, for background screening. Absent, the ordering is simply off and the
    # requirement falls back to a report filed by hand.
    certn_api_key: str = ""
    certn_base_url: str = "https://api.certn.co"
    certn_webhook_secret: str = ""


settings = Settings()
