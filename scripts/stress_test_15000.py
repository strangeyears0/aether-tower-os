#!/usr/bin/env python3
"""Aether Tower OS – Stress Test 15 000 równoległych użytkowników.

Symulacja maksymalnego obciążenia wieżowca:
15 000 pracowników (pełna pojemność Aether Tower) odpytuje jednocześnie
o stan zasobów i biurek na 100 piętrach przez publiczny AWS Load Balancer.
"""
import asyncio
import random
import time
import statistics
import aiohttp

URL_BASE = "http://a1ecee0d154b8411b8715a44273ff93a-5e8255b42e6a9891.elb.eu-central-1.amazonaws.com/api"
TOTAL_REQUESTS = 15000
CONCURRENCY = 150  # liczba równoległych sesji użytkowników
TIMEOUT_SECONDS = 15.0

async def worker(queue: asyncio.Queue, session: aiohttp.ClientSession, results: list, stats_counter: dict):
    while True:
        try:
            req_id = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        floor = random.randint(1, 100)
        url = f"{URL_BASE}/floors/{floor}/resources?date=2026-10-25"
        t0 = time.perf_counter()
        status_code = None
        error_msg = None

        try:
            async with session.get(url) as resp:
                status_code = resp.status
                await resp.read()
        except Exception as e:
            error_msg = type(e).__name__

        latency = (time.perf_counter() - t0) * 1000.0  # ms
        results.append((status_code, latency, error_msg))
        queue.task_done()

        stats_counter["done"] += 1
        done = stats_counter["done"]
        if done % 1000 == 0 or done == TOTAL_REQUESTS:
            elapsed = time.time() - stats_counter["start_time"]
            rps = done / elapsed if elapsed > 0 else 0
            errs = stats_counter["errors"]
            print(f"[{elapsed:5.1f}s] Ukończono: {done:5d} / {TOTAL_REQUESTS} ({done/TOTAL_REQUESTS*100:5.1f}%) | RPS: {rps:6.1f} | Błędy: {errs}", flush=True)

        if status_code != 200:
            stats_counter["errors"] += 1

async def main():
    print("=" * 70)
    print("   AETHER TOWER OS — STRESS TEST 15 000 UŻYTKOWNIKÓW (FULL CAPACITY)")
    print("=" * 70)
    print(f"Cel testu:          Symulacja 15 000 pracowników Aether Tower")
    print(f"Łączna liczba żądań:{TOTAL_REQUESTS}")
    print(f"Równoległe sesje:   {CONCURRENCY}")
    print(f"Zakres pięter:      1 - 100 (150 biurek na piętro)")
    print(f"Docelowy endpoint:  {URL_BASE}/floors/{{id}}/resources")
    print("=" * 70 + "\n")

    queue = asyncio.Queue()
    for i in range(TOTAL_REQUESTS):
        queue.put_nowait(i)

    results = []
    stats_counter = {
        "done": 0,
        "errors": 0,
        "start_time": time.time()
    }

    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        workers = [
            asyncio.create_task(worker(queue, session, results, stats_counter))
            for _ in range(CONCURRENCY)
        ]
        await asyncio.gather(*workers)

    total_time = time.time() - stats_counter["start_time"]
    latencies = [r[1] for r in results]
    successes = [r for r in results if r[0] == 200]
    errors = [r for r in results if r[0] != 200]

    latencies.sort()
    p50 = statistics.median(latencies) if latencies else 0
    p90 = latencies[int(len(latencies) * 0.90)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    avg_latency = statistics.mean(latencies) if latencies else 0
    min_latency = min(latencies) if latencies else 0
    max_latency = max(latencies) if latencies else 0
    avg_rps = TOTAL_REQUESTS / total_time if total_time > 0 else 0
    success_rate = (len(successes) / TOTAL_REQUESTS) * 100.0

    print("\n" + "=" * 70)
    print("           WYNIKI KOŃCOWE STRESS TESTU (15 000 REQUESTÓW)")
    print("=" * 70)
    print(f"Czas wykonania testu:        {total_time:.2f} s")
    print(f"Średnia przepustowość (RPS): {avg_rps:.2f} req/s")
    print(f"Pomyślne żądania (HTTP 200): {len(successes)} / {TOTAL_REQUESTS} ({success_rate:.2f}%)")
    print(f"Nieudane żądania / błędy:    {len(errors)}")
    print("-" * 70)
    print(f"Opóźnienie (Latency) [ms]:")
    print(f"  • Min:                     {min_latency:.1f} ms")
    print(f"  • Średnia (Mean):          {avg_latency:.1f} ms")
    print(f"  • Mediana (p50):           {p50:.1f} ms")
    print(f"  • 90. percentyl (p90):     {p90:.1f} ms")
    print(f"  • 95. percentyl (p95):     {p95:.1f} ms")
    print(f"  • 99. percentyl (p99):     {p99:.1f} ms")
    print(f"  • Max:                     {max_latency:.1f} ms")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
