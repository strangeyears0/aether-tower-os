#!/usr/bin/env python3
"""Monitor ciągłej dostępności (Zero-Downtime) podczas Rolling Update."""
import json
import time
import urllib.request
import urllib.error
import sys

URL = "http://a1ecee0d154b8411b8715a44273ff93a-5e8255b42e6a9891.elb.eu-central-1.amazonaws.com/api/meta"
VERSION_URL = "http://a1ecee0d154b8411b8715a44273ff93a-5e8255b42e6a9891.elb.eu-central-1.amazonaws.com/api/version"
DURATION = 600  # 10 minut monitoringu
INTERVAL = 0.25 # zapytanie co 250ms (4 zapytania na sekundę)

def main():
    print("=== Start monitora dostępności: sprawdzanie Zero-Downtime Rolling Update ===")
    start_time = time.time()
    success_count = 0
    failure_count = 0
    version_detected = False

    while time.time() - start_time < DURATION:
        elapsed = int(time.time() - start_time)
        try:
            req = urllib.request.Request(URL, headers={"User-Agent": "ZeroDowntimeMonitor/1.0"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    success_count += 1
                else:
                    failure_count += 1
                    print(f"[{elapsed}s] BŁĄD HTTP: {resp.status}")
        except Exception as e:
            failure_count += 1
            print(f"[{elapsed}s] WYJĄTEK POŁĄCZENIA: {e}")

        # Sprawdzamy czy nowa wersja v1.0.1 zaczęła odpowiadać
        if not version_detected:
            try:
                v_req = urllib.request.Request(VERSION_URL, headers={"User-Agent": "ZeroDowntimeMonitor/1.0"})
                with urllib.request.urlopen(v_req, timeout=1.0) as v_resp:
                    if v_resp.status == 200:
                        v_data = json.loads(v_resp.read().decode())
                        if v_data.get("version") == "1.0.1":
                            version_detected = True
                            print(f"\n[!!! {elapsed}s] WYKRYTO NOWĄ WERSJĘ v1.0.1 W KLASTRZE! Pody zostały podmienione!\n")
            except Exception:
                pass

        if success_count % 40 == 0:
            pct = 100.0 * success_count / (success_count + failure_count) if (success_count + failure_count) else 100
            print(f"[{elapsed}s] Sukcesy: {success_count} | Błędy: {failure_count} | Dostępność: {pct:.2f}% | Nowa wersja aktywna: {version_detected}")

        time.sleep(INTERVAL)

    print("\n=== PODSUMOWANIE TESTU ROLLING UPDATE ===")
    print(f"Łącznie wysłanych zapytań: {success_count + failure_count}")
    print(f"Udane (HTTP 200): {success_count}")
    print(f"Nieudane: {failure_count}")
    avail = 100.0 * success_count / (success_count + failure_count) if (success_count + failure_count) else 100
    print(f"Dostępność usługi (Uptime): {avail:.4f}%")
    if failure_count == 0 and version_detected:
        print("WYNIK: ZERO-DOWNTIME ROLLING UPDATE POTWIERDZONY! (0 przerw w dostępie)")
    else:
        print(f"WYNIK: Zarejestrowano {failure_count} przerw.")

if __name__ == "__main__":
    main()
