# WireGuard Docker Compose

Despliegue en producción de WireGuard VPN + Sidecar API usando Docker Compose.

## Estructura

```
wireguard/
├── docker-compose.yml   # Definición de servicios (wireguard + sidecar)
├── .env                 # Variables de configuración
├── config/              # Configuración persistente de WireGuard (auto-generado)
│   ├── wg_confs/        # Ficheros wg0.conf, etc.
│   ├── peer_*/          # Configuración de cada peer
│   └── peers_metadata.json  # Nombres de peers (gestionado por el sidecar)
├── peers/               # Carpeta para peers personalizados (/etc/wireguard/peers)
└── sidecar/             # Microservicio FastAPI para gestión dinámica de peers
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── main.py      # App + middleware de seguridad (X-API-Key)
        ├── models.py    # Schemas Pydantic
        ├── wg.py        # Helpers para ejecutar comandos `wg`
        ├── peers.py     # Persistencia de metadata (JSON)
        └── router.py    # Endpoints de la API
```

## Inicio rápido

### 1. Configurar variables

Edita `.env` y ajusta:
- `SERVERURL` → tu IP pública o dominio (o deja `auto`)
- `PEERS` → nombres de los peers iniciales
- `WG_API_KEY` → clave para autenticar peticiones al sidecar

### 2. Crear directorios y arrancar

```bash
mkdir -p config peers
docker compose up -d --build
```

### 3. Verificar que todo funciona

```bash
# WireGuard
docker compose exec wireguard wg show

# Sidecar healthcheck
curl http://localhost:8000/status
```

## Sidecar API

El sidecar corre como contenedor hermano de WireGuard compartiendo su network namespace (`network_mode: service:wireguard`), lo que le da acceso directo a la interfaz `wg0` para hacer cambios **sin reiniciar** (zero downtime).

### Autenticación

Todas las peticiones (excepto `/status`, `/docs`) requieren el header:

```
X-API-Key: <tu WG_API_KEY>
```

### Endpoints

| Método | Path | Descripción |
|---|---|---|
| `POST` | `/peers` | Añadir o actualizar un peer |
| `GET` | `/peers` | Listar todos los peers con metadata |
| `DELETE` | `/peers/{pubkey}` | Eliminar un peer |
| `GET` | `/status` | Healthcheck de la interfaz wg0 |

**Swagger UI**: http://localhost:8000/docs

### Ejemplos

```bash
# Añadir un peer
curl -X POST http://localhost:8000/peers \
  -H "X-API-Key: $WG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"pubkey": "<PUBLIC_KEY>", "allowed_ip": "10.13.13.10", "name": "laptop-manu"}'

# Listar peers
curl http://localhost:8000/peers -H "X-API-Key: $WG_API_KEY"

# Eliminar un peer (la pubkey debe estar URL-encoded)
curl -X DELETE "http://localhost:8000/peers/<PUBKEY_URL_ENCODED>" \
  -H "X-API-Key: $WG_API_KEY"

# Healthcheck
curl http://localhost:8000/status
```

### Peer info (GET /peers response)

```json
[
  {
    "name": "laptop-manu",
    "public_key": "abc123...",
    "endpoint": "1.2.3.4:51820",
    "allowed_ips": "10.13.13.10/32",
    "latest_handshake": 1709145600,
    "transfer_rx": 123456,
    "transfer_tx": 654321
  }
]
```

## Mantenimiento

| Acción | Comando |
|---|---|
| Ver estado WG | `docker compose exec wireguard wg show` |
| Ver logs WG | `docker compose logs -f wireguard` |
| Ver logs sidecar | `docker compose logs -f wg-sidecar` |
| Reiniciar todo | `docker compose restart` |
| Reiniciar solo sidecar | `docker compose restart wg-sidecar` |
| Actualizar imagen | `docker compose pull && docker compose up -d --build` |
| Parar todo | `docker compose down` |

## Puertos

- **51820/udp** → WireGuard VPN (debe estar abierto en el firewall)
- **8000/tcp** → Sidecar API (restringir acceso al servidor Anchor o red interna)

## Notas de producción

- `restart: unless-stopped` garantiza que ambos servicios se levanten tras reinicios
- Los volúmenes `./config` y `./peers` persisten toda la configuración
- Health check activo cada 30s con `wg show`
- Logs rotados automáticamente (max 10MB × 3 ficheros)
- `no-new-privileges` como hardening de seguridad en wireguard
- `NET_ADMIN` capability necesaria en ambos contenedores
- El módulo del kernel WireGuard debe estar disponible en el host (`/lib/modules` montado como read-only)
- `peers_metadata.json` se guarda en `./config/` para persistir entre reinicios del sidecar
