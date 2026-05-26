# Backup bazy i GitHub

## Backup jednorazowy

Na serwerze:

```bash
cd ~/memorized-scores-api
chmod +x scripts/backup_mysql.sh scripts/restore_mysql.sh
./scripts/backup_mysql.sh
ls -lh backups
```

Backup zapisze sie jako:

```text
backups/scores-db-YYYYMMDD-HHMMSS.sql.gz
```

## Przywracanie backupu

```bash
cd ~/memorized-scores-api
./scripts/restore_mysql.sh backups/scores-db-YYYYMMDD-HHMMSS.sql.gz
```

## Automatyczny backup codziennie

Otworz crona:

```bash
crontab -e
```

Dodaj:

```cron
15 3 * * * cd /home/michal/memorized-scores-api && ./scripts/backup_mysql.sh >> backups/backup.log 2>&1
```

To robi backup codziennie o 03:15.

## GitHub

Przed pierwszym commitem sprawdz:

```bash
git status
```

Nie wolno commitowac:

```text
.env
backups/
*.sql
*.sql.gz
*.zip
```

Te pliki sa ignorowane przez `.gitignore`.

Pierwszy push:

```bash
git init
git add .
git status
git commit -m "Initial FastAPI scores server"
git branch -M main
git remote add origin https://github.com/TWOJ_LOGIN/memorized-scores-api.git
git push -u origin main
```
