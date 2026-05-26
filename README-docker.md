# FastAPI + MySQL w Dockerze

## 1. Pliki na serwerze

W katalogu projektu powinny byc:

```text
app/
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

## 2. Konfiguracja

```bash
cp .env.example .env
nano .env
```

Zmien koniecznie:

```text
API_KEY=...
MYSQL_PASSWORD=...
MYSQL_ROOT_PASSWORD=...
DATABASE_URL=mysql+pymysql://scores_user:TWOJE_MYSQL_PASSWORD@mysql:3306/scores_db?charset=utf8mb4
```

`MYSQL_PASSWORD` i haslo w `DATABASE_URL` musza byc takie same.

Przyklad wygenerowania sekretow:

```bash
openssl rand -base64 32
```

## 3. Start

```bash
docker compose up -d --build
```

Sprawdzenie:

```bash
docker compose ps
curl http://127.0.0.1:12000/health
```

Poprawna odpowiedz:

```json
{"status":"ok"}
```

## 4. Logi

```bash
docker compose logs -f api
docker compose logs -f mysql
```

## 5. Test zapisu

```bash
curl -X POST http://127.0.0.1:12000/scores \
  -H "Content-Type: application/json" \
  -H "X-API-Key: TWOJ_API_KEY" \
  -d '{"id":"test-1","name":"Player","score":1234,"playerId":"player-1"}'
```

## 6. Cloudflare Tunnel pozniej

FastAPI jest wystawione na hoscie tylko lokalnie:

```text
127.0.0.1:12000
```

Cloudflare Tunnel powinien kierowac publiczny hostname na:

```text
http://127.0.0.1:12000
```

Nie trzeba otwierac portu `12000` w routerze ani publicznie w firewallu.
