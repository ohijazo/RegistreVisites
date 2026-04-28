# Guia de desplegament — Registre de Visites

## Requisits del servidor

- Ubuntu 22.04+
- Python 3.11+
- PostgreSQL 14+
- Nginx

## 1. Preparar el sistema

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip postgresql nginx
```

## 2. Crear base de dades

```bash
sudo -u postgres psql <<EOF
CREATE USER visites_user WITH PASSWORD 'CONTRASENYA_SEGURA';
CREATE DATABASE visites_db OWNER visites_user;
GRANT ALL PRIVILEGES ON DATABASE visites_db TO visites_user;
EOF
```

## 3. Descarregar l'aplicació

```bash
sudo mkdir -p /opt/visites
sudo chown $USER:$USER /opt/visites
cd /opt/visites
git clone https://github.com/ohijazo/RegistreVisites.git .
```

## 4. Entorn virtual i dependències

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 5. Configurar .env

```bash
cp .env.example .env
nano .env
```

**Camps obligatoris a configurar:**
```dotenv
DATABASE_URL=postgresql+asyncpg://visites_user:CONTRASENYA_SEGURA@localhost/visites_db

# Generar clau de xifrat (IMPORTANT: guardar en lloc segur)
# python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
ENCRYPTION_KEY=CLAU_GENERADA

# Generar secret key
# python3 -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=SECRET_GENERAT

COMPANY_NAME=Farinera Coromina - Grup AE 1897
COMPANY_ADDRESS=Adreça de l'empresa
COMPANY_EMAIL=dpo@farineracoromina.com
BASE_URL=http://IP_O_DOMINI_INTERN

ENV=production
DEBUG=false
```

## 6. Executar migracions

```bash
source venv/bin/activate
alembic upgrade head
```

## 7. Crear primer admin

```bash
python scripts/create_admin.py --email admin@farineracoromina.com --name "Administrador"
```

## 8. Crear dades inicials

```bash
python scripts/seed_legal_doc.py
```

## 9. Configurar servei systemd

```bash
sudo tee /etc/systemd/system/visites.service > /dev/null <<EOF
[Unit]
Description=Registre de Visites
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/opt/visites
EnvironmentFile=/opt/visites/.env
ExecStart=/opt/visites/venv/bin/gunicorn app.main:app \\
    --workers 2 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 127.0.0.1:8001 \\
    --timeout 30 \\
    --access-logfile /var/log/visites/access.log \\
    --error-logfile /var/log/visites/error.log
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo mkdir -p /var/log/visites
sudo chown www-data:www-data /var/log/visites
sudo chown -R www-data:www-data /opt/visites

sudo systemctl daemon-reload
sudo systemctl enable visites
sudo systemctl start visites
sudo systemctl status visites
```

## 10. Configurar Nginx

```bash
sudo tee /etc/nginx/sites-available/visites > /dev/null <<EOF
server {
    listen 80;
    server_name visites.farineracoromina.local;

    access_log /var/log/nginx/visites_access.log;
    error_log  /var/log/nginx/visites_error.log;

    add_header X-Frame-Options "DENY";
    add_header X-Content-Type-Options "nosniff";
    add_header Referrer-Policy "strict-origin";

    location /static/ {
        alias /opt/visites/static/;
        expires 30d;
    }

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 30;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/visites /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 11. Cron de manteniment

Tres tasques nocturnes: tancar visites obertes, purgar registres antics
(RGPD) i — opcionalment — anonimitzar visitants concrets sota petició
(això ja es fa des del panell `/admin/rgpd`).

```bash
sudo crontab -u www-data -e
# Afegir:

# Auto-checkout nocturn: tanca visites obertes >12h amb checkout_method='auto_eod'.
# Llindar configurable via AUTO_CLOSE_AFTER_HOURS al .env.
55 23 * * * /opt/visites/venv/bin/python /opt/visites/scripts/auto_close_visits.py >> /var/log/visites/auto_close.log 2>&1

# Neteja RGPD: elimina visites > 2 anys (article 5.1.e).
0 3 * * * /opt/visites/venv/bin/python /opt/visites/scripts/purge_old_visits.py >> /var/log/visites/purge.log 2>&1
```

## 12. Backup diari de la base de dades

```bash
sudo mkdir -p /opt/backups/visites
sudo tee /etc/cron.d/visites-backup > /dev/null <<EOF
0 2 * * * postgres pg_dump visites_db | gzip > /opt/backups/visites/visites_\$(date +\%Y\%m\%d).sql.gz
# Eliminar backups > 30 dies
0 3 * * * root find /opt/backups/visites -name "*.sql.gz" -mtime +30 -delete
EOF
```

## 13. Verificar

```bash
# Health check
curl http://localhost:8001/health

# Provar des del navegador
# http://visites.farineracoromina.local
# http://visites.farineracoromina.local/admin/login
```

## 14. Actualitzar l'aplicació

```bash
cd /opt/visites
git pull
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart visites
```

## Resolució de problemes

| Problema | Solució |
|---|---|
| `systemctl status visites` mostra error | Mirar `/var/log/visites/error.log` |
| Pàgina 503 | Verificar que PostgreSQL funciona: `sudo systemctl status postgresql` |
| No carrega la pàgina | Verificar Nginx: `sudo nginx -t` |
| Error de xifrat | Verificar `ENCRYPTION_KEY` al `.env` |
| Health check falla | `curl http://localhost:8001/health` |
