#!/usr/bin/env python3
"""
Fantacalcio Serie A -> Telegram notifier.

Ogni volta che viene eseguito:
1. Chiede a API-Football quali partite di Serie A sono LIVE in questo momento.
2. Per ognuna, recupera gli eventi (gol, assist, cartellini, sostituzioni, VAR).
3. Manda su Telegram solo gli eventi MAI notificati prima (li tiene a mente in state/state.json).

Pensato per girare via cron (es. GitHub Actions) ogni N minuti.
Ha un "paracadute" sulla quota giornaliera gratuita di API-Football (100 richieste/giorno):
se ci si avvicina al limite, si ferma da solo e avvisa su Telegram invece di sforare.
"""

import html
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ---------------------------------------------------------------------------
# Configurazione (letta da variabili d'ambiente / GitHub Secrets)
# ---------------------------------------------------------------------------

API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Nome e ID lega su API-Football. L'ID 135 è quello storicamente usato per la
# Serie A italiana, ma viene comunque fatto anche un match per nome/paese come
# rete di sicurezza nel caso l'ID sia cambiato o sbagliato: controlla su
# https://dashboard.api-football.com/soccer/ids e correggi qui se necessario.
SERIE_A_LEAGUE_ID = int(os.environ.get("SERIE_A_LEAGUE_ID", "135"))
SERIE_A_LEAGUE_NAME = "Serie A"
SERIE_A_COUNTRY = "Italy"

API_BASE_URL = "https://v3.football.api-sports.io"
STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "state.json")

# Margine di sicurezza sulla quota gratuita di 100 richieste/giorno.
DAILY_REQUEST_BUDGET = int(os.environ.get("DAILY_REQUEST_BUDGET", "90"))

EVENT_EMOJI = {
    "Goal": "⚽",
    "Card": "\U0001F7E8",
    "subst": "\U0001F504",
    "Var": "\U0001F4FA",
}

CARD_EMOJI = {
    "Yellow Card": "\U0001F7E8",
    "Red Card": "\U0001F7E5",
    "Second Yellow card": "\U0001F7E5",
}


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts} UTC] {msg}", flush=True)


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"date": "", "requests_today": 0, "warned_today": False, "fixtures": {}}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        log("state.json illeggibile o corrotto, riparto da uno stato vuoto")
        return {"date": "", "requests_today": 0, "warned_today": False, "fixtures": {}}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def reset_state_if_new_day(state):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if state.get("date") != today:
        log(f"Nuovo giorno UTC ({today}): resetto il contatore di richieste giornaliero")
        state["date"] = today
        state["requests_today"] = 0
        state["warned_today"] = False
    return state


def prune_old_fixtures(state, max_age_hours=6):
    """Rimuove dallo stato le partite non piu' toccate da ore, per non far
    crescere il file all'infinito."""
    now = time.time()
    fixtures = state.get("fixtures", {})
    to_delete = []
    for fid, data in fixtures.items():
        last_seen = data.get("last_seen", 0)
        if now - last_seen > max_age_hours * 3600:
            to_delete.append(fid)
    for fid in to_delete:
        del fixtures[fid]
    state["fixtures"] = fixtures
    return state


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID mancanti: impossibile inviare il messaggio")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code != 200:
            log(f"Errore invio Telegram ({resp.status_code}): {resp.text}")
            return False
        return True
    except requests.RequestException as e:
        log(f"Eccezione durante l'invio Telegram: {e}")
        return False


def api_football_get(path, params, state):
    """Wrapper che rispetta il budget giornaliero di richieste."""
    if state["requests_today"] >= DAILY_REQUEST_BUDGET:
        if not state.get("warned_today"):
            send_telegram_message(
                "⚠️ Fantacalcio notifier: quota giornaliera gratuita di API-Football "
                f"quasi esaurita ({DAILY_REQUEST_BUDGET} richieste). Mi fermo fino a domani (UTC)."
            )
            state["warned_today"] = True
        return None

    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", headers=headers, params=params, timeout=15)
        state["requests_today"] += 1
        if resp.status_code != 200:
            log(f"Errore API-Football su {path} ({resp.status_code}): {resp.text}")
            return None
        data = resp.json()
        errors = data.get("errors")
        if errors:
            log(f"API-Football ha restituito errori su {path}: {errors}")
        return data
    except requests.RequestException as e:
        state["requests_today"] += 1
        log(f"Eccezione chiamando API-Football {path}: {e}")
        return None


def is_serie_a(fixture_obj):
    league = fixture_obj.get("league", {})
    if league.get("id") == SERIE_A_LEAGUE_ID:
        return True
    if league.get("name") == SERIE_A_LEAGUE_NAME and league.get("country") == SERIE_A_COUNTRY:
        return True
    return False


def get_live_serie_a_fixtures(state):
    data = api_football_get("/fixtures", {"live": "all"}, state)
    if not data:
        return []
    fixtures = data.get("response", [])
    serie_a = [f for f in fixtures if is_serie_a(f)]
    log(f"Partite live totali: {len(fixtures)} | Serie A live: {len(serie_a)}")
    return serie_a


def get_fixture_events(fixture_id, state):
    data = api_football_get("/fixtures/events", {"fixture": fixture_id}, state)
    if not data:
        return []
    return data.get("response", [])


def event_signature(event):
    time_info = event.get("time", {})
    player = event.get("player", {}) or {}
    team = event.get("team", {}) or {}
    parts = [
        str(time_info.get("elapsed")),
        str(time_info.get("extra")),
        str(event.get("type")),
        str(event.get("detail")),
        str(player.get("id") or player.get("name")),
        str(team.get("id")),
    ]
    return "|".join(parts)


def format_event_message(fixture, event):
    """Messaggio su 3 righe:
    1) riga di intestazione (squadre/punteggio/minuto) in monospace piccolo
    2) riga con emoji + titolo evento, in testo normale
    3) riga di dettaglio (giocatore/assist/decisione) in monospace piccolo
    """
    teams = fixture.get("teams", {})
    home = html.escape(teams.get("home", {}).get("name", "?"))
    away = html.escape(teams.get("away", {}).get("name", "?"))
    goals = fixture.get("goals", {})
    score = f"{goals.get('home', '?')}-{goals.get('away', '?')}"

    time_info = event.get("time", {})
    minute = time_info.get("elapsed")
    extra = time_info.get("extra")
    minute_str = f"{minute}'" + (f"+{extra}" if extra else "")

    ev_type = event.get("type", "")
    detail = html.escape(event.get("detail", "") or "")
    player = html.escape((event.get("player") or {}).get("name") or "?")
    assist = (event.get("assist") or {}).get("name")
    assist = html.escape(assist) if assist else None
    team_name = html.escape((event.get("team") or {}).get("name", "?"))

    if ev_type == "Goal":
        emoji = "⚽"
        title = "GOL"
        if "Own Goal" in detail:
            title = "AUTOGOL"
        elif "Penalty" in detail:
            title = "GOL su rigore"
        middle = f"{emoji} <b>{title}</b> - {team_name}"
        bottom = player
        if assist:
            bottom += f" (assist: {assist})"
    elif ev_type == "Card":
        emoji = CARD_EMOJI.get(event.get("detail", ""), "\U0001F7E8")
        middle = f"{emoji} <b>{detail}</b> - {team_name}"
        bottom = player
    elif ev_type == "subst":
        middle = f"\U0001F504 <b>Sostituzione</b> - {team_name}"
        bottom = f"{player} entra al posto di {assist or '?'}"
    elif ev_type == "Var":
        middle = f"\U0001F4FA <b>VAR</b> - {team_name}"
        bottom = detail
    else:
        middle = f"ℹ️ <b>{html.escape(ev_type)}</b> - {team_name}"
        bottom = f"{detail} - {player}"

    top_line = f"<code>{home} {score} {away} ({minute_str})</code>"
    middle_line = middle
    bottom_line = f"<code>{bottom}</code>"

    return f"{top_line}\n{middle_line}\n{bottom_line}"


def process_fixture(fixture, state):
    fixture_id = str(fixture["fixture"]["id"])
    fixtures_state = state.setdefault("fixtures", {})
    fixture_state = fixtures_state.setdefault(fixture_id, {"notified": [], "last_seen": 0})
    fixture_state["last_seen"] = time.time()

    events = get_fixture_events(fixture["fixture"]["id"], state)
    if not events:
        return

    notified = set(fixture_state.get("notified", []))
    new_notified = list(notified)

    for event in events:
        sig = event_signature(event)
        if sig in notified:
            continue
        message = format_event_message(fixture, event)
        ok = send_telegram_message(message)
        if ok:
            new_notified.append(sig)
            log(f"Notificato: {message.splitlines()[1] if len(message.splitlines()) > 1 else message}")
        else:
            log(f"Invio fallito per evento {sig}, ritento al prossimo giro")

    fixture_state["notified"] = new_notified


def main():
    missing = [
        name
        for name, val in [
            ("API_FOOTBALL_KEY", API_FOOTBALL_KEY),
            ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
            ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID),
        ]
        if not val
    ]
    if missing:
        log(f"Variabili d'ambiente mancanti: {', '.join(missing)}. Interrompo.")
        sys.exit(1)

    state = load_state()
    state = reset_state_if_new_day(state)
    state = prune_old_fixtures(state)

    live_fixtures = get_live_serie_a_fixtures(state)
    for fixture in live_fixtures:
        process_fixture(fixture, state)

    save_state(state)
    log(f"Fine esecuzione. Richieste usate oggi: {state['requests_today']}/{DAILY_REQUEST_BUDGET}")


if __name__ == "__main__":
    main()
