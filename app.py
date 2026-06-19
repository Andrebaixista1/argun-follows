import os
import ssl
import json
import unicodedata
from collections import Counter
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, send_from_directory
from urllib3.poolmanager import PoolManager

load_dotenv(override=True)

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ARGUS_BASE_URL = "https://argus.app.br/apiargus"
ALERT_STATE_PATH = os.path.join(APP_ROOT, "alert_state.json")
ALERT_WEBHOOK_URL = "https://app.apivieiracred.com.br/webhook/api/argus-ligacoes"
ATTENDANCE_ALERT_THRESHOLD = 2.0
try:
    SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    SAO_PAULO_TZ = timezone(timedelta(hours=-3))
ALERT_WEEKDAY_START = 0  # Monday
ALERT_WEEKDAY_END = 4    # Friday
ALERT_DAY_START = (9, 30)
ALERT_DAY_END = (18, 0)
ALERT_SILENCE_START = (12, 0)
ALERT_SILENCE_END = (13, 30)
ALERT_PAUSE_START = (16, 15)
ALERT_PAUSE_END = (16, 35)
ATTENDANCE_ALERT_CONFIRMATION_SECONDS = 120

app = Flask(
    __name__,
    template_folder=os.path.join(APP_ROOT, "templates"),
    static_folder=os.path.join(APP_ROOT, "static"),
)


class ArgusTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        context = ssl.create_default_context()
        if hasattr(ssl, "OP_LEGACY_SERVER_CONNECT"):
            context.options |= ssl.OP_LEGACY_SERVER_CONNECT
        try:
            context.set_ciphers("DEFAULT:@SECLEVEL=1")
        except ssl.SSLError:
            pass

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context,
            **pool_kwargs,
        )


def env_int(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def env_float(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def normalize_status(value):
    normalized = unicodedata.normalize("NFD", str(value or ""))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").strip().upper()


def build_argus_payload():
    payload = {
        "idCampanha": env_int("ARGUS_ID_CAMPANHA"),
        "ultimosMinutos": env_int("ARGUS_ULTIMOS_MINUTOS", 5),
    }

    optional_fields = {
        "idGrupoUsuario": env_int("ARGUS_ID_GRUPO_USUARIO"),
        "idLote": env_int("ARGUS_ID_LOTE"),
        "idUsuario": env_int("ARGUS_ID_USUARIO"),
        "idStatusLigacao": env_int("ARGUS_ID_STATUS_LIGACAO"),
        "idTabulacao": env_int("ARGUS_ID_TABULACAO"),
    }

    payload.update({key: value for key, value in optional_fields.items() if value is not None})
    return payload


def argus_url():
    base_url = os.getenv("ARGUS_BASE_URL", DEFAULT_ARGUS_BASE_URL).rstrip("/")
    return f"{base_url}/report/ligacoesdetalhadas"


def argus_report_url(report_name):
    base_url = os.getenv("ARGUS_BASE_URL", DEFAULT_ARGUS_BASE_URL).rstrip("/")
    return f"{base_url}/report/{report_name}"


def campaign_name():
    explicit = os.getenv("ARGUS_CAMPANHA_NOME")
    if explicit:
        return explicit
    campaign_id = env_int("ARGUS_ID_CAMPANHA")
    if campaign_id is None:
        return "Campanha"
    return f"Campanha {campaign_id}"


def primary_group_name(groups=None):
    groups = groups or []
    if groups:
        return str(groups[0].get("grupo") or "Sem grupo").strip() or "Sem grupo"

    return os.getenv("ARGUS_GRUPO_PADRAO") or "Sem grupo"


def load_alert_state():
    try:
        with open(ALERT_STATE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return {
                    "below_threshold": bool(data.get("below_threshold")),
                    "below_since": data.get("below_since"),
                    "sent_for_current_streak": bool(data.get("sent_for_current_streak")),
                    "updatedAt": data.get("updatedAt"),
                }
            return {
                "below_threshold": bool(data),
                "below_since": None,
                "sent_for_current_streak": False,
                "updatedAt": None,
            }
    except FileNotFoundError:
        return {
            "below_threshold": False,
            "below_since": None,
            "sent_for_current_streak": False,
            "updatedAt": None,
        }
    except Exception:
        return {
            "below_threshold": False,
            "below_since": None,
            "sent_for_current_streak": False,
            "updatedAt": None,
        }


def save_alert_state(state):
    with open(ALERT_STATE_PATH, "w", encoding="utf-8") as handle:
        below_since = state.get("below_since")
        json.dump(
            {
                "below_threshold": bool(state.get("below_threshold")),
                "below_since": below_since,
                "sent_for_current_streak": bool(state.get("sent_for_current_streak")),
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_alert_silenced(now=None):
    current = now or datetime.now(SAO_PAULO_TZ)
    current_minutes = current.hour * 60 + current.minute
    start_minutes = ALERT_SILENCE_START[0] * 60 + ALERT_SILENCE_START[1]
    end_minutes = ALERT_SILENCE_END[0] * 60 + ALERT_SILENCE_END[1]
    return start_minutes <= current_minutes < end_minutes


def is_lunch_break_now(now=None):
    current = now or datetime.now(SAO_PAULO_TZ)
    if current.weekday() < ALERT_WEEKDAY_START or current.weekday() > ALERT_WEEKDAY_END:
        return False

    current_minutes = current.hour * 60 + current.minute
    start_minutes = ALERT_SILENCE_START[0] * 60 + ALERT_SILENCE_START[1]
    end_minutes = ALERT_SILENCE_END[0] * 60 + ALERT_SILENCE_END[1]
    return start_minutes <= current_minutes < end_minutes


def is_pause_break_now(now=None):
    current = now or datetime.now(SAO_PAULO_TZ)
    if current.weekday() < ALERT_WEEKDAY_START or current.weekday() > ALERT_WEEKDAY_END:
        return False

    current_minutes = current.hour * 60 + current.minute
    start_minutes = ALERT_PAUSE_START[0] * 60 + ALERT_PAUSE_START[1]
    end_minutes = ALERT_PAUSE_END[0] * 60 + ALERT_PAUSE_END[1]
    return start_minutes <= current_minutes < end_minutes


def current_break_notice(now=None):
    if is_lunch_break_now(now):
        return {
            "ativo": True,
            "tipo": "almoco",
            "inicio": "12:00",
            "fim": "13:30",
            "mensagem": (
                "Período de almoço em andamento. "
                "O volume de ligações tende a cair nesta janela. "
                "O atendimento costuma normalizar a partir das 13h30."
            ),
        }

    if is_pause_break_now(now):
        return {
            "ativo": True,
            "tipo": "pausa",
            "inicio": "16:15",
            "fim": "16:35",
            "mensagem": (
                "Período de pausa em andamento. "
                "O volume de ligações tende a cair nesta janela. "
                "O atendimento costuma normalizar às 16h35."
            ),
        }

    return {
        "ativo": False,
        "tipo": None,
        "inicio": None,
        "fim": None,
        "mensagem": "",
    }


def is_alert_allowed_now(now=None):
    current = now or datetime.now(SAO_PAULO_TZ)
    if current.weekday() < ALERT_WEEKDAY_START or current.weekday() > ALERT_WEEKDAY_END:
        return False

    current_minutes = current.hour * 60 + current.minute
    day_start_minutes = ALERT_DAY_START[0] * 60 + ALERT_DAY_START[1]
    day_end_minutes = ALERT_DAY_END[0] * 60 + ALERT_DAY_END[1]
    if not (day_start_minutes <= current_minutes < day_end_minutes):
        return False

    return not is_alert_silenced(current)


def send_attendance_alert(attendance_rate, group_name):
    token = os.getenv("ARGUS_TOKEN_SIGNATURE")
    if not token:
        raise RuntimeError("Configure ARGUS_TOKEN_SIGNATURE no arquivo .env")

    payload = {
        "grupo": group_name,
        "atendimento": round(attendance_rate, 2),
        "mensagem": (
            f"O grupo {group_name} está abaixo do esperado: "
            f"{attendance_rate:.2f}% de atendimento."
        ),
        "status": "abaixo_esperado",
    }

    response = requests.post(
        ALERT_WEBHOOK_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Webhook HTTP {response.status_code}: {response.text[:200] or response.reason}"
        )

    return payload


def pick_status(call):
    candidates = (
        "statusLigacaoDesc",
        "statusLigacao",
        "descricaoStatusLigacao",
        "descStatusLigacao",
        "statusDesc",
        "resultadoLigacao",
        "resultado",
        "resultadoLigacao",
        "tabulacaoDesc",
    )

    for key in candidates:
        value = call.get(key)
        if value:
            return str(value).strip()

    return "Sem status"


def build_group_metrics(calls):
    ignored_groups = {"ACEITE - GIOVANA", "EUROPA 5", "INATIVO"}
    groups = {}
    for call in calls:
        group_id = call.get("idGrupoUsuario") or 0
        group_name = call.get("grupoOrigem") or call.get("grupo") or "Sem grupo"
        if group_name.strip().upper() in ignored_groups:
            continue

        key = str(group_id)
        status = pick_status(call)

        if key not in groups:
            groups[key] = {
                "idGrupoUsuario": group_id,
                "grupo": group_name,
                "total": 0,
                "attendance": 0,
                "statuses": Counter(),
            }

        groups[key]["total"] += 1
        groups[key]["statuses"][status] += 1
        if status.upper() == "ATENDIMENTO":
            groups[key]["attendance"] += 1

    result = []
    for group in groups.values():
        total = group["total"]
        attendance = group["attendance"]
        result.append(
            {
                "idGrupoUsuario": group["idGrupoUsuario"],
                "grupo": group["grupo"],
                "total": total,
                "attendance": attendance,
                "attendanceRate": (attendance / total * 100) if total else 0,
                "byStatus": [
                    {"status": status, "count": count}
                    for status, count in group["statuses"].most_common()
                ],
            }
        )

    return sorted(result, key=lambda item: item["total"], reverse=True)


def fetch_ligacoes_detalhadas():
    token = os.getenv("ARGUS_TOKEN_SIGNATURE")
    if not token:
        raise RuntimeError("Configure ARGUS_TOKEN_SIGNATURE no arquivo .env")

    payload = build_argus_payload()
    if not payload["idCampanha"]:
        raise RuntimeError("Configure ARGUS_ID_CAMPANHA no arquivo .env")

    session = requests.Session()
    endpoint = argus_url()
    if endpoint.startswith("https://argus.app.br"):
        session.mount("https://argus.app.br", ArgusTLSAdapter())

    response = session.post(
        endpoint,
        headers={
            "Token-Signature": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=20,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        message = data.get("descStatus") or response.text[:200] or response.reason
        raise RuntimeError(f"Argus HTTP {response.status_code}: {message}")

    calls = data.get("ligacoesDetalhadas") or []
    total = data.get("qtdeRegistros")
    if total is None:
        total = len(calls)

    status_counter = Counter(pick_status(call) for call in calls)
    by_status = [
        {"status": status, "count": count}
        for status, count in status_counter.most_common()
    ]
    by_status.sort(key=lambda item: 0 if normalize_status(item["status"]) == "ATENDIMENTO" else 1)
    attendance_count = status_counter.get("ATENDIMENTO", 0)
    attendance_rate = (attendance_count / total * 100) if total else 0
    local_now = datetime.now(SAO_PAULO_TZ)
    groups = build_group_metrics(calls)
    group_name = primary_group_name(groups)

    alert_state = load_alert_state()
    alert_result = {
        "enabled": False,
        "sent": False,
        "belowThreshold": attendance_rate < ATTENDANCE_ALERT_THRESHOLD,
        "threshold": ATTENDANCE_ALERT_THRESHOLD,
        "silenced": is_alert_silenced(local_now),
        "allowedNow": is_alert_allowed_now(local_now),
        "confirmationSeconds": ATTENDANCE_ALERT_CONFIRMATION_SECONDS,
        "streakSeconds": 0,
    }
    break_notice = current_break_notice(local_now)

    webhook_url = os.getenv("ARGUS_ATTENDANCE_WEBHOOK_URL", ALERT_WEBHOOK_URL)
    below_threshold = attendance_rate < ATTENDANCE_ALERT_THRESHOLD

    if below_threshold:
        below_since = parse_iso_datetime(alert_state.get("below_since"))
        if not alert_state.get("below_threshold") or below_since is None:
            below_since = local_now
            alert_state["below_threshold"] = True
            alert_state["sent_for_current_streak"] = False
            alert_state["below_since"] = below_since.isoformat()
            save_alert_state(alert_state)

        alert_result["streakSeconds"] = max(0, int((local_now - below_since).total_seconds()))
        alert_result["enabled"] = True
        alert_result["readyToSend"] = alert_result["streakSeconds"] >= ATTENDANCE_ALERT_CONFIRMATION_SECONDS
        alert_result["sentForCurrentStreak"] = bool(alert_state.get("sent_for_current_streak"))

        if (
            alert_result["allowedNow"]
            and alert_result["readyToSend"]
            and not alert_state.get("sent_for_current_streak")
        ):
            alert_result["sent"] = True
            alert_result["webhook"] = webhook_url
            webhook_payload = {
                "grupo": group_name,
                "atendimento": round(attendance_rate, 2),
                "mensagem": (
                    f"O grupo {group_name} está abaixo do esperado. "
                    f"Atendimento atual: {attendance_rate:.2f}%. "
                    f"Regra de 2 minutos confirmada."
                ),
                "status": "abaixo_esperado",
                "threshold": ATTENDANCE_ALERT_THRESHOLD,
                "confirmationSeconds": ATTENDANCE_ALERT_CONFIRMATION_SECONDS,
            }

            response = requests.post(
                webhook_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=webhook_payload,
                timeout=600,
            )

            if response.status_code >= 400:
                alert_result["sent"] = False
                alert_result["error"] = (
                    f"Webhook HTTP {response.status_code}: "
                    f"{response.text[:200] or response.reason}"
                )
            else:
                alert_result["payload"] = webhook_payload
                alert_state["sent_for_current_streak"] = True
                save_alert_state(alert_state)
    else:
        if alert_state.get("below_threshold") or alert_state.get("sent_for_current_streak"):
            alert_state = {
                "below_threshold": False,
                "below_since": None,
                "sent_for_current_streak": False,
            }
            save_alert_state(alert_state)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": int(total),
        "attendanceRate": attendance_rate,
        "byStatus": by_status,
        "byGroup": groups,
        "alerta": alert_result,
        "periodoAviso": break_notice,
        "argus": {
            "codStatus": data.get("codStatus"),
            "descStatus": data.get("descStatus"),
            "endOfTable": data.get("endOfTable"),
            "idProxPagina": data.get("idProxPagina"),
            "idCampanha": data.get("idCampanha"),
        },
        "request": {
            "endpoint": endpoint,
            "payload": payload,
        },
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/logo01.png")
def logo01():
    return send_from_directory(APP_ROOT, "logo01.png")


@app.get("/api/metrics")
def metrics():
    try:
        return jsonify({"ok": True, "data": fetch_ligacoes_detalhadas()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


if __name__ == "__main__":
    app.run(host=os.getenv("FLASK_HOST", "127.0.0.1"), port=env_int("FLASK_PORT", 5055), debug=True)
