# Aether Tower OS — System Rezerwacji Stanowisk Pracy w Skali 15 000 Biurek

[![Kubernetes](https://img.shields.io/badge/Kubernetes-1.30-326CE5?logo=kubernetes&logoColor=white)](https://kubernetes.io/)
[![AWS EKS](https://img.shields.io/badge/AWS-EKS%20%7C%20ECR%20%7C%20CodePipeline-FF9900?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)](https://www.terraform.io/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2016-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

System orkiestracji i zarządzania stanowiskami pracy typu Hot-Desk oraz strefami projektowymi w 100-piętrowym wieżowcu biurowym **Aether Tower** (łączna pojemność: **15 000 stanowisk**). 

Projekt stanowi praktyczną realizację pracy inżynierskiej, demonstrującą wdrożenie wysoko dostępnej architektury mikroserwisowej w chmurze **Amazon Web Services (AWS)** z wykorzystaniem orkiestratora **Amazon EKS**, potoku **CI/CD (AWS CodePipeline v2)**, mechanizmów autoskalowania **HPA** oraz trwałych wolumenów blokowych **AWS EBS gp3**.

---

## 🏗️ Architektura Systemu

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           INTERNET / KLIENT                                             │
└────────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                     │ HTTP :80 / :8080
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    AWS Network Load Balancer (NLB)                                      │
└────────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ AMAZON EKS (v1.30) — Namespace: `aether-tower`                                                          │
│                                                                                                         │
│   ┌───────────────────────────┐      /api/* proxy      ┌────────────────────────────────────────────┐   │
│   │   Deployment: frontend    │ ─────────────────────▶ │      Deployment: reservation-service       │   │
│   │   (NGINX Unprivileged)    │                        │          (FastAPI + asyncpg)               │   │
│   │   Replicas: 2             │                        │          HPA: 2 – 6 replik (CPU > 50%)     │   │
│   └───────────────────────────┘                        └──────┬───────────────────────────────┬─────┘   │
│                                                               │                               │         │
│                                         async SQLAlchemy      │           HTTP (asynchroniczny)         │
│                                                               ▼                               ▼         │
│                                                ┌──────────────────────────┐   ┌─────────────────────┐   │
│                                                │ StatefulSet: postgres    │   │ user-notification   │   │
│                                                │ (PostgreSQL 16)          │   │ (FastAPI, mail/log) │   │
│                                                └────────────┬─────────────┘   └─────────────────────┘   │
│                                                             │ Dynamic Provisioning                      │
│                                                             ▼                                           │
│                                                ┌──────────────────────────┐                             │
│                                                │  AWS EBS gp3 CSI Driver  │                             │
│                                                │  (10 GiB PersistentVol)  │                             │
│                                                └──────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Kluczowe Funkcjonalności

- **Skala 15 000 stanowisk:** 100 pięter po 150 biurek podzielonych na 4 strefy funkcjonalne:
  - **Alpha (1–30):** *Focus & Deep Work* (kabiny akustyczne, monitory 4K, stacje i9).
  - **Beta (31–70):** *Collaboration & Project* (zespoły projektowe, tablice interaktywne).
  - **Gamma (71–110):** *Agile Teams* (elastyczne stanowiska zespołowe).
  - **Delta (111–150):** *Hot Desks & Dual 4K* (dynamiczne biurka rotacyjne).
- **Architektoniczny UI (Paper & Ink):** Interfejs zaprojektowany w stylu redakcyjnym (typografia *Fraunces*, *Schibsted Grotesk*, *DM Mono*, ciepły papier `#F2EEE5`, cynobrowy akcent `#D9461F`), plan piętra w czytelnym układzie sektorów 2×2.
- **Odporność na konflikty (Race Conditions):** Równoległe próby rezerwacji tego samego biurka są blokowane na poziomie bazy danych (`UNIQUE (resource_id, reservation_date)`), zwracając kod `409 Conflict` bez błędów serwera.
- **Bezpieczeństwo kontenerów:** Obrazy zbudowane z zasadą najmniejszych uprawnień (`runAsNonRoot: true`, dedykowany użytkownik `appuser` UID/GID `10001`).

---

## 🚀 Uruchomienie Lokalne (Docker Compose)

Wymagania: zainstalowany **Docker Desktop**.

```bash
# 1. Klonowanie repozytorium
git clone https://github.com/strangeyears0/aether-tower-os.git
cd aether-tower-os

# 2. Uruchomienie całego stosu (jedno polecenie)
docker compose up --build
```

Kolejność startu z uwzględnieniem healthchecków:
1. `postgres` (baza PostgreSQL 16)
2. `user-notification-service` (mikroserwis powiadomień)
3. `reservation-service` (główny backend API)
4. `seed` (automatyczne zasilenie: 15 000 stanowisk, 300 użytkowników, 280 rezerwacji)
5. `frontend` (panel graficzny WWW)

### Punkty dostępu lokalnego:
| Usługa | Adres URL |
|---|---|
| **Aether Tower OS (Panel WWW)** | [http://localhost:8080](http://localhost:8080) |
| **Reservation API (Dokumentacja Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Notification API (Swagger)** | [http://localhost:8001/docs](http://localhost:8001/docs) |
| **Baza PostgreSQL** | `localhost:5432` (`aether` / `aether_dev_password`) |

*Reset bazy i ponowne zasilenie:*
```bash
docker compose run --rm seed python /scripts/seed.py --reset
```

---

## ☁️ Wdrożenie w Chmurze AWS (Terraform + EKS)

Wymagania: **AWS CLI**, **Terraform >= 1.5**, skonfigurowane uprawnienia IAM.

Katalog `infrastructure/` zawiera pełną definicję **Infrastructure as Code (IaC)**:
- Dedykowany **VPC** (2 podsieci publiczne, 2 prywatne, Internet Gateway, NAT Gateway).
- Zarządzany klaster **Amazon EKS v1.30** z grupą węzłów roboczych EC2 Spot (`t3.medium`, Amazon Linux 2023).
- **AWS CodePipeline v2** połączony z GitHubem i **AWS CodeBuild** do budowania kontenerów i wdrożeń Kustomize.
- Rejestry **Amazon ECR** z automatycznym tagowaniem hashem commita.

```bash
cd infrastructure
terraform init
terraform plan
terraform apply -auto-approve
```

---

## 📊 Badania Empiryczne i Eksperymenty (Rozdział 5 Pracy Inżynierskiej)

W ramach pracy inżynierskiej przeprowadzono serię 4 eksperymentów badawczych w środowisku produkcyjnym AWS:

### 1. Eksperyment 1: Trwałość danych przy awarii węzła (StatefulSet + EBS CSI)
- **Scenariusz:** Utworzenie rezerwacji `F042-D002` (ID 281), a następnie nagłe uśmiercenie poda bazy poleceniem `kubectl delete pod postgres-0`.
- **Wynik:** Kontroler StatefulSet odtworzył pod w **16 sekund**, automatycznie podpinając ten sam wolumen AWS EBS (`pvc-d087d92d...`).
- **Wskaźnik RPO:** **0 sekund (zero utraty danych)**.

### 2. Eksperyment 2: Horyzontalne autoskalowanie podów (HPA)
- **Scenariusz:** Syntetyczne obciążenie wielowątkowe (25 wątków, 7 750 zapytań o losowe piętra w 90s).
- **Wynik:** Obciążenie CPU wzrosło skokowo do **240%**, a kontroler HPA przeskalował `reservation-service` z **2 do 6 podów**.
- **Skuteczność:** 100% zapytań obsłużonych z kodem HTTP 200 (0 błędów).

### 3. Eksperyment 3: Bezprzerwowa aktualizacja wersji (Zero-Downtime Rolling Update)
- **Scenariusz:** Wypchnięcie nowej wersji kodu `v1.0.1` do GitHuba (`commit 87bf9c1`), wyzwolenie potoku CI/CD AWS CodePipeline i nieustanny pomiar dostępności z częstotliwością 4 zapytań na sekundę (co 250 ms).
- **Wynik:** Pełne przejście na wersję `v1.0.1` w 157. sekundzie testu.
- **Wskaźnik Uptime:** **100.000%** (0 błędów, 0 odrzuconych połączeń przy strategii `maxUnavailable: 0`).

### 4. Eksperyment 4: Stress Test Maksymalnego Obciążenia (15 000 Pracowników)
- **Scenariusz:** Symulacja jednoczesnego zapytania od 15 000 pracowników wieżowca (150 sesji równoległych w skrypcie [`scripts/stress_test_15000.py`](scripts/stress_test_15000.py)).
- **Wynik:**
  - **Liczba zapytań:** 15 000 / 15 000 udanych (**100.00% success rate**, 0 błędów).
  - **Czas trwania:** 101.56 s (~1 min 41 s).
  - **Średnia przepustowość (RPS):** **147.70 req/s**.
  - **Mediana czasu odpowiedzi (p50):** **671.6 ms** (p90: 2.44 s).
  - **Autoskalowanie:** CPU osiągnęło 398%, utrzymując 6 stabilnych replik na instancjach EC2 Spot.

---

## 🛠️ Zestaw Narzędzi i Skryptów

W katalogu [`scripts/`](scripts/) znajdują się narzędzia ułatwiające replikację wyników badań:
- [`seed.py`](scripts/seed.py) – zasilenie bazy 15 000 stanowisk i 300 profilami użytkowników.
- [`load_test.py`](scripts/load_test.py) – generator obciążenia wielowątkowego dla HPA.
- [`monitor_rolling_update.py`](scripts/monitor_rolling_update.py) – monitorowanie SLA i dostępności (Zero-Downtime).
- [`stress_test_15000.py`](scripts/stress_test_15000.py) – asynchroniczny stress test dla 15 000 równoległych użytkowników.

---

## 📜 Licencja

Projekt zrealizowany w celach akademickich i badawczych w ramach pracy inżynierskiej.
