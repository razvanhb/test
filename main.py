import firebase_admin
from firebase_admin import credentials, firestore
import requests
import threading
import time
import os
import json

# 1. Configurare Autentificare Firebase
# Pe server va citi din variabila de mediu, iar local va citi din fișierul JSON
if os.environ.get('FIREBASE_CREDENTIALS'):
    cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
    cred = credentials.Certificate(cred_dict)
else:
    cred = credentials.Certificate('serviceAccountKey.json')

firebase_admin.initialize_app(cred)
db = firestore.client()

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1537355642518372452/iKYta63pCmmRFYBN8fQnFo7hn-e8CTkNAoYNpnxjc48VRj8o3O-EzNa_OtBePsez4oxo"

# Dictionar în memorie pentru a ține evidența timer-elor active
active_timers = {}

def send_discord_alert(code, exp_time_str, nickname, game_id):
    """Trimite mesajul pe Discord și marchează alerta ca trimisă în Firebase."""
    payload = {
        "content": f"@everyone @here 🚨 **ATENȚIE! URMEAZĂ UN JAF!** 🚨\nMagazinul **{code}** va se poate da în **5 minute** (la ora **{exp_time_str}**)!\n*Jaf inițiat precedent de:* **{nickname}** (ID: {game_id})"
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code in [200, 204]:
            print(f"[{code}] Alerta trimisă cu succes pe Discord!")
            # Marcăm în Firebase că alerta a plecat
            db.collection('stores').document(code).update({'alertSent': True})
        else:
            print(f"[{code}] Eroare Webhook Discord: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[{code}] Eroare la trimiterea alertei: {e}")

def on_snapshot(col_snapshot, changes, read_time):
    """Ascultă în timp real modificările din colecția 'stores'."""
    for change in changes:
        doc = change.document
        data = doc.to_dict()
        code = doc.id

        # Când se adaugă un jaf nou sau se modifică o stare
        if change.type.name in ['ADDED', 'MODIFIED']:
            if data.get('cooldownUntil') and not data.get('alertSent'):
                cooldown_dt = data['cooldownUntil']
                end_timestamp = cooldown_dt.timestamp()
                now_timestamp = time.time()

                # Momentul țintă: cu 5 minute (300 secunde) înainte de expirare
                target_alert_time = end_timestamp - (5 * 60)
                delay = target_alert_time - now_timestamp

                if delay > 0:
                    # Dacă exista deja un timer vechi pentru acest magazin, îl oprim
                    if code in active_timers:
                        active_timers[code].cancel()

                    ora_expirarii = cooldown_dt.strftime('%H:%M')
                    nickname = data.get('initiatedByNickname', 'Anonim')
                    game_id = data.get('initiatedBy', 'N/A')

                    print(f"[Magazin {code}] Jaf detectat! Alerta programată peste {round(delay / 60, 1)} minute.")

                    # Creăm un thread care va executa trimiterea alertei după expirarea timpului
                    timer_thread = threading.Timer(
                        delay, 
                        send_discord_alert, 
                        args=[code, ora_expirarii, nickname, game_id]
                    )
                    active_timers[code] = timer_thread
                    timer_thread.start()

        # Dacă un admin șterge cooldown-ul din dashboard
        elif change.type.name == 'REMOVED':
            if code in active_timers:
                active_timers[code].cancel()
                del active_timers[code]
                print(f"[Magazin {code}] Cooldown anulat de un admin. Timer oprit.")

if __name__ == "__main__":
    print("Botul Python ascultă baza de date Firebase...")
    
    # Pornim ascultătorul Firestore pe colecția 'stores'
    col_query = db.collection('stores')
    query_watch = col_query.on_snapshot(on_snapshot)

    # Ținem procesul principal activ
    while True:
        time.sleep(1)