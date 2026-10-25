#!/usr/bin/env python3
"""Skrypt generujący sztuczne obciążenie HTTP dla klastra EKS (Test HPA)."""
import concurrent.futures
import time
import urllib.request
import random
import sys

URL_BASE = "http://a1ecee0d154b8411b8715a44273ff93a-5e8255b42e6a9891.elb.eu-central-1.amazonaws.com/api"
DURATION_SECONDS = 90
CONCURRENCY = 25

def send_request():
    floor = random.randint(1, 100)
    url = f"{URL_BASE}/floors/{floor}/resources?date=2026-10-25"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status
    except Exception as e:
        return str(e)

def main():
    print(f"=== Rozpoczynanie testu obciążeniowego HPA ({CONCURRENCY} wątków, {DURATION_SECONDS} s) ===")
    start_time = time.time()
    total_requests = 0
    errors = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        while time.time() - start_time < DURATION_SECONDS:
            futures = [executor.submit(send_request) for _ in range(CONCURRENCY * 2)]
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                total_requests += 1
                if res != 200:
                    errors += 1
            elapsed = int(time.time() - start_time)
            print(f"[{elapsed}s / {DURATION_SECONDS}s] Wysłano żądań: {total_requests} (błędy: {errors})")
            time.sleep(0.05)

    print(f"=== Zakończono test obciążeniowy: {total_requests} żądań, {errors} błędów ===")

if __name__ == "__main__":
    main()
