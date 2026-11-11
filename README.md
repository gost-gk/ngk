# Зеркало ГК на время набегов спамботов, ошибок 504 и т.п.

Тут: https://gcode.space/#!/

Для работы БД требуется установить расширение «pg_trgm»:
* `sudo -u postgres psql`
* `\c ngk`
* `CREATE EXTENSION pg_trgm;`
* `\q`

## Установка

```bash
apt install -y git nginx postgresql redis-server curl ca-certificates
```

```bash
su - postgres -c "psql -qc \"CREATE ROLE ngk LOGIN PASSWORD 'change-me'\""
su - postgres -c "psql -qc 'CREATE DATABASE ngk OWNER ngk'"
su - postgres -c "psql -d ngk -qc 'CREATE EXTENSION pg_trgm'"
su - postgres -c "psql -d ngk -f /dev/stdin" < schema.sql
su - postgres -c "psql -d ngk -qc 'GRANT USAGE, CREATE ON SCHEMA public TO ngk'"
su - postgres -c "psql -d ngk -qc 'GRANT ALL ON ALL TABLES IN SCHEMA public TO ngk'"
su - postgres -c "psql -d ngk -qc 'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ngk'"
```

```bash
adduser --system --ingroup www-data --home /home/ngk --shell /bin/bash ngk
su - ngk -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
su - ngk -c "git clone https://github.com/gost-gk/ngk /home/ngk/ngk"
su - ngk -c "cd /home/ngk/ngk && /home/ngk/.local/bin/uv sync"
su - ngk -c "cp src/ngk/.env.example src/ngk/.env"
# заполнить src/ngk/.env, далее:
su - ngk -c "/home/ngk/ngk/.venv/bin/python -c 'import secrets; print(\"SECRET_KEY=\" + secrets.token_hex(32)); print(\"API_PRIVATE_KEY=\" + secrets.token_hex(32))'"
```

```bash
mkdir -p /home/ngk/ngk/logs /home/ngk/ngk/dumps /var/log/nginx/ngk
chown -R ngk:www-data /home/ngk/ngk/logs /home/ngk/ngk/dumps
```

```bash
tee /etc/systemd/system/ngk-api.service <<'EOF'
[Unit]
Description=ngk api
After=network.target postgresql.service redis-server.service

[Service]
User=ngk
Group=www-data
WorkingDirectory=/home/ngk/ngk/src
ExecStart=/home/ngk/ngk/.venv/bin/python -m ngk.serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
tee /etc/systemd/system/ngk-comments.service <<'EOF'
[Unit]
Description=ngk comments scanner
After=network.target postgresql.service redis-server.service

[Service]
User=ngk
WorkingDirectory=/home/ngk/ngk/src
ExecStart=/home/ngk/ngk/.venv/bin/python -m ngk.scan_comments
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
tee /etc/systemd/system/ngk-posts.service <<'EOF'
[Unit]
Description=ngk posts scanner
After=network.target postgresql.service redis-server.service

[Service]
User=ngk
WorkingDirectory=/home/ngk/ngk/src
ExecStart=/home/ngk/ngk/.venv/bin/python -m ngk.fetch_posts
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

```bash
tee /etc/nginx/sites-available/gcode.space.conf <<'EOF'
server {
    listen 80;
    server_name gcode.space;

    root /home/ngk/ngk/static;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:30002/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /socket.io/ {
        proxy_pass http://127.0.0.1:30002/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /db_dumps/ {
        autoindex on;
        alias /home/ngk/ngk/db_dumps/;
    }
}
EOF
ln -s /etc/nginx/sites-available/gcode.space.conf /etc/nginx/sites-enabled/
nginx -t
```

```bash
systemctl enable --now postgresql redis-server nginx ngk-api ngk-comments ngk-posts
```

