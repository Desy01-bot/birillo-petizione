import csv
import io
import os
import re
import sqlite3
import time
import requests
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup, escape
from werkzeug.security import check_password_hash

BASE_DIR = Path(__file__).resolve().parent


def load_dotenv_file(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


load_dotenv_file(BASE_DIR / ".env")
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "petition.db"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# Per il primo avvio puoi usare ADMIN_PASSWORD. In produzione usa ADMIN_PASSWORD_HASH.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "cambia-questa-password")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
SECRET_KEY = os.environ.get("SECRET_KEY", "sviluppo-cambia-questa-chiave-segreta")
GOOGLE_SHEETS_WEBHOOK = os.environ.get("GOOGLE_SHEETS_WEBHOOK", "")
SHEETS_SECRET = os.environ.get("SHEETS_SECRET", "")

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Piccolo rate limiter in memoria: utile per demo, non sostituisce protezioni server in produzione.
_submissions_by_ip: dict[str, list[float]] = {}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


DEFAULT_SETTINGS = {
    # Testi generali
    "site_title": os.environ.get("PETITION_TITLE", "Liberiamo il gatto prelevato senza autorizzazione"),
    "meta_description": "Raccolta firme per chiedere il rientro in sicurezza di un gatto prelevato senza autorizzazione.",
    "nav_brand": "🐾 Raccolta firme",
    "nav_admin_label": "Area admin",
    "petition_location": os.environ.get("PETITION_LOCATION", ""),
    "petition_goal": os.environ.get("PETITION_GOAL", "500"),

    # Hero / intestazioni homepage
    "hero_eyebrow": "Petizione civica",
    "hero_title": os.environ.get("PETITION_TITLE", "Liberiamo il gatto prelevato senza autorizzazione"),
    "hero_subtitle": "Chiediamo che il gatto venga riportato in sicurezza e che siano rispettati il benessere dell'animale e il ruolo di chi se ne prendeva cura.",
    "stats_text": "firme raccolte su",

    # Form firma
    "form_title": "Firma la petizione",
    "form_name_label": "Nome e cognome *",
    "form_name_placeholder": "Es. Maria Rossi",
    "form_email_label": "Email facoltativa",
    "form_email_placeholder": "nome@email.it",
    "form_city_label": "Città facoltativa",
    "form_city_placeholder": "Es. Roma",
    "form_comment_label": "Messaggio facoltativo",
    "form_comment_placeholder": "Scrivi un breve messaggio di sostegno",
    "form_public_label": "Mostra il mio nome nella lista pubblica delle ultime firme.",
    "form_privacy_label": "Accetto il trattamento dei dati per questa raccolta firme.",
    "form_privacy_link_label": "Leggi l'informativa",
    "form_button_label": "Firma ora",
    "form_success_message": "Firma registrata. Grazie per il tuo sostegno!",

    # Sezioni contenuto
    "why_title": "Perché questa petizione",
    "why_text": "Un gatto seguito e accudito è stato prelevato senza l'autorizzazione di chi se ne prendeva cura.\nCon questa raccolta firme chiediamo un confronto responsabile, il rientro dell'animale in un contesto sicuro e il rispetto delle persone che hanno garantito cure, cibo e attenzione.",
    "ask_title": "Cosa chiediamo",
    "ask_items": "Verificare immediatamente dove si trovi il gatto e le sue condizioni.\nConsentire a chi lo accudiva di avere notizie chiare e documentate.\nFavorire una soluzione che tuteli prima di tutto il benessere dell'animale.",
    "recent_title": "Ultime firme pubbliche",
    "recent_empty_text": "Ancora nessuna firma pubblica. Puoi essere tra le prime persone a sostenere la petizione.",
    "footer_text": "Raccolta firme indipendente. Prima della pubblicazione reale, personalizza testi, dati del titolare e informativa privacy.",

    # Privacy
    "privacy_title": "Informativa privacy",
    "privacy_intro": "Questa è una bozza tecnica da personalizzare prima della pubblicazione. Indica sempre il titolare del trattamento, un contatto, la finalità della raccolta, il tempo di conservazione e le modalità per chiedere cancellazione o rettifica.",
    "privacy_data_title": "Dati raccolti",
    "privacy_data_text": "Nome, eventuale email, eventuale città, eventuale messaggio e data della firma.",
    "privacy_purpose_title": "Finalità",
    "privacy_purpose_text": "I dati sono usati esclusivamente per gestire e documentare questa raccolta firme.",
    "privacy_rights_title": "Diritti",
    "privacy_rights_text": "Ogni firmatario può chiedere l'accesso, la modifica o la cancellazione dei dati scrivendo al contatto indicato dal titolare.",
    "privacy_back_label": "Torna alla petizione",

    # Layout e aspetto
    "layout_variant": "split",
    "hero_style": "gradient",
    "bg_color": "#fff7ed",
    "panel_color": "#ffffff",
    "text_color": "#211a17",
    "muted_color": "#76655d",
    "accent_color": "#e66b2e",
    "accent_dark_color": "#b94616",
    "soft_color": "#ffe1ca",
    "border_color": "#f1c9ad",
    "max_width": "1120",
    "border_radius": "28",
    "button_radius": "999",
    "base_font_size": "16",
    "custom_css": "",

    # Visibilità sezioni
    "show_admin_link": "1",
    "show_location": "1",
    "show_stats": "1",
    "show_why_section": "1",
    "show_ask_section": "1",
    "show_recent_section": "1",
    "show_footer": "1",
}

SETTINGS_GROUPS = [
    {
        "title": "Intestazioni principali",
        "description": "Modifica titolo del sito, menu e testo grande della homepage.",
        "fields": [
            {"key": "site_title", "label": "Titolo scheda browser", "type": "text", "max": 180},
            {"key": "meta_description", "label": "Descrizione per motori di ricerca", "type": "textarea", "rows": 2, "max": 300},
            {"key": "nav_brand", "label": "Testo/logo in alto a sinistra", "type": "text", "max": 80},
            {"key": "nav_admin_label", "label": "Testo link area admin", "type": "text", "max": 60},
            {"key": "hero_eyebrow", "label": "Sopratitolo", "type": "text", "max": 80},
            {"key": "hero_title", "label": "Titolo grande homepage", "type": "textarea", "rows": 2, "max": 220},
            {"key": "hero_subtitle", "label": "Sottotitolo homepage", "type": "textarea", "rows": 4, "max": 700},
            {"key": "petition_location", "label": "Luogo/quartiere", "type": "text", "max": 120},
            {"key": "petition_goal", "label": "Obiettivo firme", "type": "number", "min": 1, "max": 1000000},
            {"key": "stats_text", "label": "Testo accanto al numero firme", "type": "text", "max": 80},
        ],
    },
    {
        "title": "Modulo firma",
        "description": "Cambia titoli, etichette, placeholder e messaggi del form.",
        "fields": [
            {"key": "form_title", "label": "Titolo form", "type": "text", "max": 90},
            {"key": "form_name_label", "label": "Etichetta nome", "type": "text", "max": 80},
            {"key": "form_name_placeholder", "label": "Placeholder nome", "type": "text", "max": 100},
            {"key": "form_email_label", "label": "Etichetta email", "type": "text", "max": 80},
            {"key": "form_email_placeholder", "label": "Placeholder email", "type": "text", "max": 100},
            {"key": "form_city_label", "label": "Etichetta città", "type": "text", "max": 80},
            {"key": "form_city_placeholder", "label": "Placeholder città", "type": "text", "max": 100},
            {"key": "form_comment_label", "label": "Etichetta messaggio", "type": "text", "max": 80},
            {"key": "form_comment_placeholder", "label": "Placeholder messaggio", "type": "textarea", "rows": 2, "max": 180},
            {"key": "form_public_label", "label": "Testo consenso nome pubblico", "type": "textarea", "rows": 2, "max": 250},
            {"key": "form_privacy_label", "label": "Testo consenso privacy", "type": "textarea", "rows": 2, "max": 250},
            {"key": "form_privacy_link_label", "label": "Testo link privacy", "type": "text", "max": 80},
            {"key": "form_button_label", "label": "Testo pulsante firma", "type": "text", "max": 60},
            {"key": "form_success_message", "label": "Messaggio dopo firma", "type": "text", "max": 160},
        ],
    },
    {
        "title": "Sezioni della homepage",
        "description": "Modifica titoli e contenuti dei blocchi sotto al form.",
        "fields": [
            {"key": "why_title", "label": "Titolo sezione 1", "type": "text", "max": 100},
            {"key": "why_text", "label": "Testo sezione 1", "type": "textarea", "rows": 6, "max": 1200},
            {"key": "ask_title", "label": "Titolo sezione 2", "type": "text", "max": 100},
            {"key": "ask_items", "label": "Elenco richieste, una per riga", "type": "textarea", "rows": 6, "max": 1200},
            {"key": "recent_title", "label": "Titolo ultime firme", "type": "text", "max": 100},
            {"key": "recent_empty_text", "label": "Testo se non ci sono firme", "type": "textarea", "rows": 2, "max": 250},
            {"key": "footer_text", "label": "Testo fondo pagina", "type": "textarea", "rows": 3, "max": 500},
        ],
    },
    {
        "title": "Informativa privacy",
        "description": "Testi mostrati nella pagina privacy. Personalizzali prima della pubblicazione reale.",
        "fields": [
            {"key": "privacy_title", "label": "Titolo privacy", "type": "text", "max": 100},
            {"key": "privacy_intro", "label": "Introduzione privacy", "type": "textarea", "rows": 4, "max": 900},
            {"key": "privacy_data_title", "label": "Titolo dati raccolti", "type": "text", "max": 100},
            {"key": "privacy_data_text", "label": "Testo dati raccolti", "type": "textarea", "rows": 3, "max": 700},
            {"key": "privacy_purpose_title", "label": "Titolo finalità", "type": "text", "max": 100},
            {"key": "privacy_purpose_text", "label": "Testo finalità", "type": "textarea", "rows": 3, "max": 700},
            {"key": "privacy_rights_title", "label": "Titolo diritti", "type": "text", "max": 100},
            {"key": "privacy_rights_text", "label": "Testo diritti", "type": "textarea", "rows": 3, "max": 700},
            {"key": "privacy_back_label", "label": "Testo link torna indietro", "type": "text", "max": 80},
        ],
    },
    {
        "title": "Layout e stile",
        "description": "Cambia struttura, colori, dimensioni e anche CSS personalizzato.",
        "fields": [
            {"key": "layout_variant", "label": "Layout homepage", "type": "select", "options": [("split", "Testo a sinistra + form a destra"), ("centered", "Titolo centrato + form sotto"), ("compact", "Compatto")]} ,
            {"key": "hero_style", "label": "Sfondo intestazione", "type": "select", "options": [("gradient", "Sfumato"), ("plain", "Semplice"), ("soft", "Morbido con bordo")]} ,
            {"key": "bg_color", "label": "Colore sfondo", "type": "color"},
            {"key": "panel_color", "label": "Colore riquadri", "type": "color"},
            {"key": "text_color", "label": "Colore testo", "type": "color"},
            {"key": "muted_color", "label": "Colore testo secondario", "type": "color"},
            {"key": "accent_color", "label": "Colore principale pulsanti", "type": "color"},
            {"key": "accent_dark_color", "label": "Colore pulsanti hover", "type": "color"},
            {"key": "soft_color", "label": "Colore morbido/progress bar", "type": "color"},
            {"key": "border_color", "label": "Colore bordi", "type": "color"},
            {"key": "max_width", "label": "Larghezza massima sito in px", "type": "number", "min": 760, "max": 1500},
            {"key": "border_radius", "label": "Arrotondamento riquadri", "type": "number", "min": 0, "max": 60},
            {"key": "button_radius", "label": "Arrotondamento pulsanti", "type": "number", "min": 0, "max": 999},
            {"key": "base_font_size", "label": "Grandezza base testo", "type": "number", "min": 14, "max": 22},
            {"key": "custom_css", "label": "CSS personalizzato facoltativo", "type": "textarea", "rows": 8, "max": 5000},
        ],
    },
    {
        "title": "Mostra o nascondi parti del sito",
        "description": "Attiva/disattiva sezioni senza cancellarne i testi.",
        "fields": [
            {"key": "show_admin_link", "label": "Mostra link Area admin nel sito pubblico", "type": "checkbox"},
            {"key": "show_location", "label": "Mostra luogo/quartiere", "type": "checkbox"},
            {"key": "show_stats", "label": "Mostra contatore firme", "type": "checkbox"},
            {"key": "show_why_section", "label": "Mostra sezione 'Perché questa petizione'", "type": "checkbox"},
            {"key": "show_ask_section", "label": "Mostra sezione 'Cosa chiediamo'", "type": "checkbox"},
            {"key": "show_recent_section", "label": "Mostra ultime firme pubbliche", "type": "checkbox"},
            {"key": "show_footer", "label": "Mostra fondo pagina", "type": "checkbox"},
        ],
    },
]


def all_setting_fields():
    for group in SETTINGS_GROUPS:
        for field in group["fields"]:
            yield field


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signatures (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT,
                city TEXT,
                comment TEXT,
                privacy_consent INTEGER NOT NULL DEFAULT 0,
                public_display INTEGER NOT NULL DEFAULT 1,
                ip_hash TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signatures_created_at ON signatures(created_at)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO site_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, str(value), now),
            )
        conn.commit()


def get_site_settings():
    settings = DEFAULT_SETTINGS.copy()
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM site_settings").fetchall()
    for row in rows:
        if row["key"] in settings:
            settings[row["key"]] = row["value"]
    return settings


def setting_bool(settings, key):
    return str(settings.get(key, "0")) == "1"


def setting_int(settings, key, fallback=0):
    try:
        return int(settings.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


@app.template_filter("nl2br")
def nl2br(value):
    escaped = escape(value or "")
    return Markup(str(escaped).replace("\n", "<br>"))


@app.context_processor
def inject_template_helpers():
    return {"setting_bool": setting_bool, "setting_int": setting_int}


def validate_setting(field, raw_value):
    field_type = field.get("type", "text")
    key = field["key"]

    if field_type == "checkbox":
        return "1" if raw_value == "on" else "0"

    value = (raw_value or "").strip()

    if field_type in {"text", "textarea"}:
        max_len = field.get("max")
        if max_len:
            value = value[: int(max_len)]
        return value

    if field_type == "number":
        try:
            number = int(value)
        except ValueError:
            number = int(DEFAULT_SETTINGS.get(key, "0"))
        if "min" in field:
            number = max(number, int(field["min"]))
        if "max" in field:
            number = min(number, int(field["max"]))
        return str(number)

    if field_type == "color":
        return value if HEX_COLOR_RE.match(value) else DEFAULT_SETTINGS.get(key, "#000000")

    if field_type == "select":
        allowed = {option[0] for option in field.get("options", [])}
        return value if value in allowed else DEFAULT_SETTINGS.get(key, next(iter(allowed), ""))

    return value


def save_site_settings(form_data):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with get_db() as conn:
        for field in all_setting_fields():
            key = field["key"]
            value = validate_setting(field, form_data.get(key))
            conn.execute(
                """
                INSERT INTO site_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
        conn.commit()


def count_signatures():
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM signatures").fetchone()
        return row["total"]


def get_recent_public_signatures(limit=8):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT full_name, city, comment, created_at
            FROM signatures
            WHERE public_display = 1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_latest_signatures(limit=25):
    with get_db() as conn:
        return conn.execute(
            """
            SELECT id, full_name, email, city, comment, created_at, public_display
            FROM signatures
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_daily_stats(days=30):
    start = datetime.now(timezone.utc) - timedelta(days=days - 1)
    labels = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
    totals = {label: 0 for label in labels}
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS total
            FROM signatures
            WHERE created_at >= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (start.date().isoformat(),),
        ).fetchall()
    for row in rows:
        if row["day"] in totals:
            totals[row["day"]] = row["total"]
    return {"labels": labels, "values": [totals[label] for label in labels]}


def clean_text(value: str, max_len: int) -> str:
    value = (value or "").strip()
    value = re.sub(r"\s+", " ", value)
    return value[:max_len]


def client_ip():
    # Se sei dietro reverse proxy, configura correttamente ProxyFix prima di fidarti di X-Forwarded-For.
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"


def simple_ip_hash(value: str) -> str:
    # Evita di salvare l'IP in chiaro; non è pensato come meccanismo crittografico forte.
    import hashlib

    salt = app.secret_key.encode("utf-8")
    return hashlib.sha256(salt + value.encode("utf-8")).hexdigest()


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    window_seconds = 10 * 60
    max_submissions = 5
    entries = [t for t in _submissions_by_ip.get(ip, []) if now - t < window_seconds]
    _submissions_by_ip[ip] = entries
    if len(entries) >= max_submissions:
        return True
    entries.append(now)
    return False


def admin_password_ok(password: str) -> bool:
    if ADMIN_PASSWORD_HASH:
        return check_password_hash(ADMIN_PASSWORD_HASH, password)
    return password == ADMIN_PASSWORD


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapper


def public_context():
    settings = get_site_settings()
    goal = setting_int(settings, "petition_goal", 500)
    total = count_signatures()
    progress = min(round((total / goal) * 100), 100) if goal else 0
    return settings, goal, total, progress


@app.before_request
def ensure_db():
    init_db()


@app.get("/")
def index():
    settings, goal, total, progress = public_context()
    return render_template(
        "index.html",
        s=settings,
        total=total,
        goal=goal,
        progress=progress,
        recent=get_recent_public_signatures(),
        ask_items=[item.strip() for item in settings.get("ask_items", "").splitlines() if item.strip()],
    )

def backup_signature_to_google_sheet(payload):
    if not GOOGLE_SHEETS_WEBHOOK:
        return

    try:
        data = payload.copy()
        data["secret"] = SHEETS_SECRET

        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK,
            json=data,
            timeout=5
        )

        if response.status_code >= 400:
            app.logger.warning("Backup Google Sheets non riuscito: %s", response.text)

    except Exception as error:
        app.logger.warning("Backup Google Sheets non riuscito: %s", error)


@app.post("/firma")
def sign_petition():
    settings = get_site_settings()
    ip = client_ip()

    if is_rate_limited(ip):
        flash("Hai inviato troppe firme in poco tempo. Riprova più tardi.", "error")
        return redirect(url_for("index"))

    # Honeypot antispam: questo campo resta vuoto per gli utenti reali.
    if request.form.get("website"):
        flash("Invio non valido.", "error")
        return redirect(url_for("index"))

    full_name = clean_text(request.form.get("full_name", ""), 120)
    email = clean_text(request.form.get("email", ""), 160).lower()
    city = clean_text(request.form.get("city", ""), 80)
    comment = clean_text(request.form.get("comment", ""), 600)
    privacy_consent = request.form.get("privacy_consent") == "on"
    public_display = request.form.get("public_display") == "on"

    errors = []

    if len(full_name) < 2:
        errors.append("Inserisci nome e cognome o un nominativo valido.")

    if email and not EMAIL_RE.match(email):
        errors.append("Inserisci un indirizzo email valido oppure lascia il campo vuoto.")

    if not privacy_consent:
        errors.append("Per firmare devi accettare l'informativa privacy.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("index"))

    signature_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO signatures (
                id, full_name, email, city, comment, privacy_consent,
                public_display, ip_hash, user_agent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signature_id,
                full_name,
                email or None,
                city or None,
                comment or None,
                1,
                1 if public_display else 0,
                simple_ip_hash(ip),
                clean_text(request.headers.get("User-Agent", ""), 240),
                created_at,
            ),
        )
        conn.commit()

    backup_signature_to_google_sheet({
        "id": signature_id,
        "full_name": full_name,
        "email": email or "",
        "city": city or "",
        "comment": comment or "",
        "public_display": public_display,
        "created_at": created_at,
    })

    flash(settings.get("form_success_message", DEFAULT_SETTINGS["form_success_message"]), "success")
    return redirect(url_for("index"))


@app.get("/api/stats")
def api_stats():
    settings = get_site_settings()
    return jsonify(
        {
            "total": count_signatures(),
            "goal": setting_int(settings, "petition_goal", 500),
            "daily": get_daily_stats(30),
        }
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    settings = get_site_settings()
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and admin_password_ok(password):
            session.clear()
            session["admin_logged_in"] = True
            flash("Accesso effettuato.", "success")
            return redirect(request.args.get("next") or url_for("admin_dashboard"))
        flash("Credenziali non valide.", "error")
    return render_template("admin_login.html", s=settings)


@app.post("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    flash("Sei uscito dall'area amministratore.", "success")
    return redirect(url_for("admin_login"))


@app.get("/admin")
@admin_required
def admin_dashboard():
    settings, goal, total, progress = public_context()
    latest = get_latest_signatures()
    daily_stats = get_daily_stats(30)
    return render_template(
        "admin_dashboard.html",
        s=settings,
        total=total,
        goal=goal,
        progress=progress,
        latest=latest,
        daily_stats=daily_stats,
    )


@app.route("/admin/personalizza", methods=["GET", "POST"])
@admin_required
def admin_customize():
    if request.method == "POST":
        save_site_settings(request.form)
        flash("Modifiche salvate. Apri la homepage per vedere il risultato.", "success")
        return redirect(url_for("admin_customize"))

    settings = get_site_settings()
    return render_template("admin_customize.html", s=settings, groups=SETTINGS_GROUPS)


@app.get("/admin/export.csv")
@admin_required
def export_csv():
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, full_name, email, city, comment, public_display, created_at
            FROM signatures
            ORDER BY created_at ASC
            """
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "nome", "email", "citta", "commento", "visibile_pubblicamente", "data_firma_utc"])
    for row in rows:
        writer.writerow([
            row["id"],
            row["full_name"],
            row["email"] or "",
            row["city"] or "",
            row["comment"] or "",
            "si" if row["public_display"] else "no",
            row["created_at"],
        ])

    filename = f"firme-petizione-{datetime.now().date().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/privacy")
def privacy():
    settings = get_site_settings()
    return render_template("privacy.html", s=settings)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
