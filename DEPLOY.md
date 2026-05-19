# Guia de desplegament — Registre de Visites

> Segueix la mateixa convenció que `fitxes-tecniques` i `comandes-venda`: codi a `/var/www/<app>/`, propietari `www-data`, Apache com a reverse proxy, port backend `50003`, DNS `visitesfc.agrienergia.local`.

## Requisits del servidor

- Ubuntu 22.04+
- Python 3.11+
- PostgreSQL 14+
- Apache 2.4+ (amb mòduls `proxy`, `proxy_http`, `headers`, `rewrite`, `expires`)

## 1. Preparar el sistema

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip postgresql apache2 git
sudo a2enmod proxy proxy_http headers rewrite expires
```

## 2. Crear base de dades

```bash
sudo -u postgres psql <<EOF
CREATE DATABASE visites_db;
CREATE USER visites_user WITH PASSWORD 'CONTRASENYA_SEGURA';
GRANT ALL PRIVILEGES ON DATABASE visites_db TO visites_user;

\c visites_db
ALTER DATABASE visites_db OWNER TO visites_user;
ALTER SCHEMA public OWNER TO visites_user;
GRANT ALL ON SCHEMA public TO visites_user;
GRANT CREATE ON SCHEMA public TO visites_user;
EOF
```

> **IMPORTANT** (PostgreSQL 15+): l'esquema `public` no és escrivible per defecte tot i tenir `ALL PRIVILEGES`. Cal canviar-ne el propietari i donar `CREATE`. Si no, `alembic upgrade head` fallarà amb `permission denied for schema public`.
>
> **Contrasenya BD**: evitar caràcters que trenquen URLs (`@`, `:`, `/`, `?`, `#`, `;`). Si calen, codificar-los (`@`→`%40`, etc.).

## 3. Descarregar l'aplicació

```bash
cd /var/www
sudo git clone https://github.com/ohijazo/RegistreVisites.git visites
sudo chown -R www-data:www-data /var/www/visites

sudo mkdir -p /var/log/visites
sudo chown www-data:www-data /var/log/visites
```

## 4. Entorn virtual i dependències

```bash
cd /var/www/visites
sudo -u www-data python3 -m venv venv
sudo -u www-data venv/bin/pip install --upgrade pip
sudo -u www-data venv/bin/pip install -r requirements.txt
sudo -u www-data venv/bin/pip install gunicorn
```

## 5. Configurar .env

```bash
sudo -u www-data cp .env.example .env
sudo nano .env
sudo chmod 600 .env
sudo chown www-data:www-data .env
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
BASE_URL=http://visitesfc.agrienergia.local

ENV=production
DEBUG=false
```

## 6. Executar migracions

```bash
cd /var/www/visites
sudo -u www-data venv/bin/alembic upgrade head
```

## 7. Crear primer admin

```bash
sudo -u www-data venv/bin/python scripts/create_admin.py --email admin@farineracoromina.com --name "Administrador"
```

## 8. Crear dades inicials

```bash
sudo -u www-data venv/bin/python scripts/seed_legal_doc.py
```

## 9. Configurar servei systemd

```bash
sudo tee /etc/systemd/system/visites.service > /dev/null <<EOF
[Unit]
Description=Registre de Visites - Backend
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/var/www/visites
EnvironmentFile=/var/www/visites/.env
ExecStart=/var/www/visites/venv/bin/gunicorn app.main:app \\
    --workers 2 \\
    --worker-class uvicorn.workers.UvicornWorker \\
    --bind 127.0.0.1:50003 \\
    --timeout 30 \\
    --access-logfile /var/log/visites/access.log \\
    --error-logfile /var/log/visites/error.log
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable visites
sudo systemctl start visites
sudo systemctl status visites
```

## 10. Configurar Apache (VirtualHost)

```bash
sudo tee /etc/apache2/sites-available/visites.conf > /dev/null <<'EOF'
<VirtualHost *:80>
    ServerName visitesfc.agrienergia.local

    Header always set X-Frame-Options        "DENY"
    Header always set X-Content-Type-Options "nosniff"
    Header always set Referrer-Policy        "strict-origin"

    LimitRequestBody 2097152

    Alias /static/ /var/www/visites/static/
    <Directory /var/www/visites/static/>
        Require all granted
        Options -Indexes
        ExpiresActive On
        ExpiresDefault "access plus 30 days"
    </Directory>

    ProxyPreserveHost On
    ProxyPass        /static/ !
    ProxyPass        / http://127.0.0.1:50003/
    ProxyPassReverse / http://127.0.0.1:50003/

    ErrorLog  ${APACHE_LOG_DIR}/visites-error.log
    CustomLog ${APACHE_LOG_DIR}/visites-access.log combined
</VirtualHost>
EOF

sudo a2ensite visites.conf
sudo apache2ctl configtest
sudo systemctl reload apache2
```

DNS intern: afegir un registre A `visitesfc.agrienergia.local` → IP del servidor.

## 11. Email amb Microsoft 365 — Opció ràpida amb Power Automate

Alternativa a Graph API quan no es pot obtenir admin consent del tenant
(o per anar més ràpid). El flux corre amb les credencials del compte
M365 propietari, sense necessitat de cap app a Entra ID ni rol especial.

### a) Crear el flux

1. Anar a **https://make.powerautomate.com** i fer login amb la
   bústia que ha d'enviar (p.ex. `coromina@agrienergia.com`).
2. **Crear** → **Flux instantani** → seleccionar el trigger
   "**Quan es rep una sol·licitud HTTP**" (When an HTTP request is
   received).
3. Al primer pas, definir l'esquema JSON del body que rebrà:

   ```json
   {
       "type": "object",
       "properties": {
           "to": {
               "type": "array",
               "items": { "type": "string" }
           },
           "subject": { "type": "string" },
           "body": { "type": "string" }
       }
   }
   ```

4. **+ Nou pas** → buscar **"Office 365 Outlook"** → acció
   "**Enviar un correu electrònic (V2)**". Omplir:
   - **A**: `join(triggerBody()?['to'], ';')` (o seleccionar dinàmicament
     `to` i el connector ja el separa).
     Tip: si la UI no t'admet l'array, posa-hi una expressió:
     `join(triggerBody()?['to'], ';')`.
   - **Assumpte**: contingut dinàmic → `subject`.
   - **Cos**: contingut dinàmic → `body`.
5. (Opcional, recomanat) Validar el header secret abans d'enviar:
   - Inserir un pas **Condició** abans de l'acció Outlook.
   - Condició: `triggerOutputs()?['headers']?['X-Webhook-Secret']`
     **és igual a** `<el-teu-secret>`.
   - Si fals → "Resposta" amb codi 401.
6. **Desar** el flux.

### b) Apuntar la URL del webhook

Tornar al primer pas (HTTP request). Apareix la **HTTP POST URL**
(generada automàticament). Còpia-la.

### c) Configuració al `.env`

```bash
EMAIL_BACKEND=power_automate
POWER_AUTOMATE_WEBHOOK_URL=https://prod-XX.westeurope.logic.azure.com:443/workflows/.../triggers/manual/paths/invoke?...
POWER_AUTOMATE_SECRET=<un-string-llarg-aleatori>

# Destinataris per defecte
EXPECTED_NOTIFY_RECIPIENTS=cap@empresa.com
```

Per generar un secret bo:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### d) Verificació

`systemctl restart visites`, crea una visita prevista i comprova
`/admin/audit-logs?action=expected_visit_email_sent_auto`. Si falla,
mira `expected_visit_email_failed_auto` per veure l'error retornat
per Power Automate.

### Notes

- El compte que ha creat el flux és qui apareix com a remitent dels
  emails. Si aquesta persona deixa l'empresa, el flux deixarà de
  funcionar — caldrà recrear-lo amb un altre compte.
- Limits: usuari Power Automate Free: ~100 execucions/dia. Plans M365
  E3/E5/Business Premium: pràcticament il·limitat per a aquest ús.
- Per a integració més robusta i auditable a llarg termini, considerar
  migrar a Graph API (secció següent).

## 12. Email amb Microsoft 365 (Graph API, OAuth 2.0)

Configuració recomanada per a comptes M365 corporatives. Sobreviu a la
deprecació de SMTP AUTH i no requereix mantenir cap contrasenya
d'aplicació al servidor.

### a) Registrar una app a Entra ID

1. Anar a **https://entra.microsoft.com** → Identidad → Aplicaciones →
   Registros de aplicaciones → **Nuevo registro**.
2. Nombre: `Registre Visites`. Tipus de cuenta: **Solo este inquilino**.
   Redirect URI: deixar buit.
3. A la pàgina de l'app, apuntar:
   - **Application (client) ID**
   - **Directory (tenant) ID**
4. **Certificados y secretos** → Nuevo secreto → apuntar el `Valor`.
5. **Permisos de API** → + Agregar permiso → Microsoft Graph → **Permisos
   de aplicación** → marcar `Mail.Send` → Agregar.
6. Clicar **"Conceder consentimiento de administrador"** (cal Global Admin
   o Application Administrator del tenant).

### b) Restringir l'app a una sola bústia (recomanat)

Per defecte un `Mail.Send` d'aplicació pot enviar com a qualsevol bústia
del tenant. Cal restringir-ho amb una `ApplicationAccessPolicy`:

```powershell
# Cal el rol Exchange Administrator
Connect-ExchangeOnline

New-ApplicationAccessPolicy `
    -AppId <client_id> `
    -PolicyScopeGroupId <bústia@empresa.com> `
    -AccessRight RestrictAccess `
    -Description "Restringir l'app del registre de visites a una sola bústia"
```

### c) Configuració al `.env`

```bash
EMAIL_BACKEND=graph_ms
MS_TENANT_ID=<directory_tenant_id>
MS_CLIENT_ID=<application_client_id>
MS_CLIENT_SECRET=<valor_del_secret>
MS_SENDER_EMAIL=coromina@empresa.com

# Destinataris per defecte de la notificació al crear una prevista
EXPECTED_NOTIFY_RECIPIENTS=cap@empresa.com,recepcio@empresa.com
```

### d) Verificació

Després del reinici (`systemctl restart visites`), crea una visita
prevista des de `/admin/expected/new`. Si tot està bé:
- L'email arriba al destinatari (mira també la carpeta de Spam).
- A `/admin/audit-logs?action=expected_visit_email_sent_auto` apareix
  la traça.

Si falla:
- Mira `/admin/audit-logs?action=expected_visit_email_failed_auto` —
  el camp `detail.error` indica què ha passat.
- Errors típics: `401` (token), `403` (permís Mail.Send no concedit /
  ApplicationAccessPolicy bloca la bústia), `404` (bústia no existeix).

## 13. Cron de manteniment

Tres tasques nocturnes: tancar visites obertes, purgar registres antics
(RGPD) i — opcionalment — anonimitzar visitants concrets sota petició
(això ja es fa des del panell `/admin/rgpd`).

```bash
sudo crontab -u www-data -e
# Afegir:

# Auto-checkout nocturn: tanca visites obertes >12h amb checkout_method='auto_eod'.
# Llindar configurable via AUTO_CLOSE_AFTER_HOURS al .env.
55 23 * * * /var/www/visites/venv/bin/python /var/www/visites/scripts/auto_close_visits.py >> /var/log/visites/auto_close.log 2>&1

# Neteja RGPD: elimina visites > 2 anys (article 5.1.e).
0 3 * * * /var/www/visites/venv/bin/python /var/www/visites/scripts/purge_old_visits.py >> /var/log/visites/purge.log 2>&1
```

## 14. Backup diari de la base de dades

```bash
sudo mkdir -p /opt/backups/visites
sudo tee /etc/cron.d/visites-backup > /dev/null <<EOF
0 2 * * * postgres pg_dump visites_db | gzip > /opt/backups/visites/visites_\$(date +\%Y\%m\%d).sql.gz
# Eliminar backups > 30 dies
0 3 * * * root find /opt/backups/visites -name "*.sql.gz" -mtime +30 -delete
EOF
```

## 15. Verificar

```bash
# Health check (directe al backend)
curl http://localhost:50003/health

# Provar des del navegador
# http://visitesfc.agrienergia.local
# http://visitesfc.agrienergia.local/admin/login
```

## 16. Actualitzar l'aplicació

```bash
cd /var/www/visites
sudo -u www-data git pull
sudo -u www-data venv/bin/pip install -r requirements.txt
sudo -u www-data venv/bin/alembic upgrade head
sudo systemctl restart visites
```

## Resolució de problemes

| Problema | Solució |
|---|---|
| `systemctl status visites` mostra error | Mirar `/var/log/visites/error.log` o `journalctl -u visites -n 50` |
| Error 502/503 a Apache | Gunicorn caigut: `sudo systemctl restart visites` |
| Error de BD | `sudo systemctl status postgresql` |
| No carrega la pàgina | Validar Apache: `sudo apache2ctl configtest` |
| Error de xifrat | Verificar `ENCRYPTION_KEY` al `.env` |
| Health check falla | `curl http://localhost:50003/health` |
