import firebase_admin
from firebase_admin import credentials, firestore
import requests
import threading
import time
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# --- NOU: Un mic server HTTP pentru planul GRATUIT Render ---
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Botul este Online 24/7!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

# Pornim serverul de health check pe un thread secundar
threading.Thread(target=run_dummy_server, daemon=True).start()
# -----------------------------------------------------------

# 1. Autentificare Firebase
if os.environ.get('FIREBASE_CREDENTIALS'):
    cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate('serviceAccountKey.json')

firebase_admin.initialize_app(cred)
db = firestore.client()

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1537355642518372452/iKYta63pCmmRFYBN8fQnFo7hn-e8CTkNAoYNpnxjc48VRj8o3O-EzNa_OtBePsez4oxo"
active_timers = {}

def send_discord_alert(code, exp_time_str, nickname, game_id):
    payload = {
        "content": f"@everyone @here 🚨 **ATENȚIE! URMEAZĂ UN JAF!** 🚨\nMagazinul **{code}** va ieși din cooldown în **5 minute** (la ora **{exp_time_str}**)!\n*Jaf inițiat de:* **{nickname}** (ID: {game_id})"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code in [200, 204]:
            print(f"[{code}] Alerta trimisă cu succes pe Discord!")
            db.collection('stores').document(code).update({'alertSent': True})
    except Exception as e:
        print(f"[{code}] Eroare la trimitere: {e}")

def on_snapshot(col_snapshot, changes, read_time):
    for change in changes:
        doc = change.document
        data = doc.to_dict()
        code = doc.id

        if change.type.name in ['ADDED', 'MODIFIED']:
            if data.get('cooldownUntil') and not data.get('alertSent'):
                cooldown_dt = data['cooldownUntil']
                end_timestamp = cooldown_dt.timestamp()
                now_timestamp = time.time()

                target_alert_time = end_timestamp - (5 * 60)
                delay = target_alert_time - now_timestamp

                if delay > 0:
                    if code in active_timers:
                        active_timers[code].cancel()

                    ora_expirarii = cooldown_dt.strftime('%H:%M')
                    nickname = data.get('initiatedByNickname', 'Anonim')
                    game_id = data.get('initiatedBy', 'N/A')

                    print(f"[Magazin {code}] Jaf detectat! Timer setat la {round(delay / 60, 1)} minute.")

                    timer_thread = threading.Timer(
                        delay, 
                        send_discord_alert, 
                        args=[code, ora_expirarii, nickname, game_id]
                    )
                    active_timers[code] = timer_thread
                    timer_thread.start()

        elif change.type.name == 'REMOVED':
            if code in active_timers:
                active_timers[code].cancel()
                del active_timers[code]
                print(f"[Magazin {code}] Cooldown anulat.")

if __name__ == "__main__":
    print("Botul Python ascultă baza de date Firebase...")
    col_query = db.collection('stores')
    query_watch = col_query.on_snapshot(on_snapshot)

    while True:
        time.sleep(1)