# Seguridad en la VPN WireGuard

## El problema

Una VPN convencional expone la superficie de ataque antes de que el usuario se autentique: el servidor escucha en un puerto público, responde a cualquier paquete y revela así su existencia a cualquier escáner. Si además la clave privada WireGuard del cliente se guarda en disco en texto plano, cualquier proceso con acceso al sistema de ficheros —o cualquier snapshot/backup— puede robarla.

Anchor resuelve ambos problemas en capas independientes.

---

## Visión general del flujo

```
Cliente                                   Servidor
  │                                          │
  │  1. UDP knock (186 B, cifrado ECIES)     │
  │ ─────────────────────────────────────── ▶│ knock listener :62201
  │                                          │  • descifra con SPA privkey
  │                                          │  • verifica TOTP + anti-replay
  │                                          │  • registra peer (AllowedIPs = ip/32)
  │                                          │  • crea lease state=onboarding (5 min)
  │                                          │
  │  2. Túnel onboarding (AllowedIPs = 10.13.13.1/32)
  │ ◀────────────────────────────────────── ▶│ WireGuard :51820
  │    solo puede hablar con el servidor     │
  │                                          │
  │  3. POST /auth/login  (por el túnel)     │
  │ ─────────────────────────────────────── ▶│ API :17017
  │ ◀─────────────── JWT ─────────────────── │
  │                                          │
  │  4. POST /vpn/promote  (con JWT)         │
  │ ─────────────────────────────────────── ▶│
  │ ◀──── assigned_ip, routes, server_pubkey ┤
  │                                          │  • lease → state=active
  │                                          │  • AllowedIPs actualizados
  │                                          │
  │  5. Túnel activo (AllowedIPs = 10.13.13.1/32)
  │ ◀────────────────────────────────────── ▶│
```

El servidor **nunca responde al knock** (UDP sin respuesta). Si el paquete es inválido o el TOTP es incorrecto, simplemente se descarta en silencio. Un escáner externo no puede distinguir si el puerto existe.

---

## Las claves del sistema

### 1. Par de claves SPA — X25519 (servidor)

**Para qué sirve:** cifrar el paquete de knock UDP. Permite que el cliente envíe su identidad y clave WireGuard sin que nadie que intercepte el tráfico pueda leerlos.

| Elemento | Dónde vive |
|---|---|
| Clave privada (`SPA_PRIVKEY_B64`) | Variable de entorno del servidor → memoria del proceso. Nunca se escribe en disco dentro del contenedor. |
| Clave pública | Incluida en el provision token que se entrega al cliente. Se puede compartir libremente. |

**Generación:** al arrancar el servidor, si `SPA_PRIVKEY_B64` no está configurada, se auto-genera una clave efímera para esa sesión y se imprime en el log para que el admin la fije en `.env`. La clave se almacena en `/srv/anchor/server/.env` (fuera del contenedor) con permisos restrictivos.

**Por qué es segura:** un atacante que capture el paquete UDP solo ve bytes aleatorios. Sin la clave privada del servidor no puede descifrar el contenido ni determinar quién envió el knock.

---

### 2. Par de claves WireGuard — Curve25519 (cliente)
#### TODO - Someone can sniff the file and play manually. Need server ip rules to prevent
**Para qué sirve:** autenticar el túnel WireGuard. La clave pública se envía en el knock cifrado; el servidor la registra como peer autorizado.

| Elemento | Dónde vive |
|---|---|
| Clave privada | Generada en memoria en cada `anc vpn up`. Se escribe en `/dev/shm/anc-vpn.conf` (tmpfs RAM, nunca toca disco), se pasa a `wg-quick` y el fichero se borra inmediatamente. |
| Clave pública | Se incluye en el paquete de knock cifrado. El servidor la almacena en el lease de MongoDB y la entrega al sidecar WireGuard. |

**`/dev/shm` vs `/tmp`:** `/dev/shm` es un sistema de ficheros montado en RAM por el kernel. Los datos desaparecen al apagar el equipo y nunca se graban en disco. El fichero se crea con permisos `0600` (solo el propietario puede leerlo) y se elimina tan pronto como `wg-quick` termina de leer la configuración.

**Por qué es segura:** la clave privada WireGuard nunca persiste en disco. Si el portátil del usuario es robado, no hay clave que robar. Si otro proceso en el mismo equipo intenta leer `/dev/shm/anc-vpn.conf`, los permisos `0600` lo impiden, y para cuando el atacante reaccionara el fichero ya habría sido borrado.

---

### 3. Semilla TOTP — base32 (por usuario)

**Para qué sirve:** autenticar el knock sin contraseña y sin que el servidor responda. Es el segundo factor que hace que un knock capturado en red sea inútil para un atacante.

| Elemento | Dónde vive |
|---|---|
| Semilla plaintext | Solo visible en el momento de provisión (QR en terminal). Jamás se guarda en texto plano. |
| Semilla cifrada (`otp_seed_enc`) | MongoDB, cifrada con AES-256-GCM + HKDF-SHA256 usando la clave maestra del vault. |
| App de autenticador | Google Authenticator, Authy u otra app TOTP en el dispositivo del usuario. |

**Rotación:** el admin puede revocar y regenerar la semilla con `DELETE /vpn/admin/users/{u}/otp` + `POST /vpn/admin/users/{u}/otp`. El usuario debe re-escanear el QR.

**Ventana de validez:** ±30 segundos (1 paso TOTP). Un código capturado es inútil pasados 30 s, y la protección anti-replay (ver más adelante) lo inutiliza incluso dentro de esa ventana.

---

### 4. Par de claves WireGuard — servidor

**Para qué sirve:** cifrar y autenticar el túnel WireGuard en el lado del servidor. Generado por la imagen Docker de `linuxserver/wireguard` al arrancar.

| Elemento | Dónde vive |
|---|---|
| Clave privada | Dentro del contenedor `wireguard`, en `/config/wg_confs/wg0.conf`. Solo accesible como root o desde el sidecar. |
| Clave pública | Distribuida a los clientes en el provision token (`server_pubkey`). |

---

### 5. JWT de sesión

**Para qué sirve:** autenticar las llamadas HTTP al servidor Anchor (login, promote, sync) una vez que el túnel onboarding está activo.

| Elemento | Dónde vive |
|---|---|
| Token JWT | Memoria del proceso cliente + `~/.config/anchor/credentials.toml` (solo lectura del propietario). |
| Secret de firma | Variable de entorno del servidor (`JWT_SECRET`). Nunca en código ni en el repositorio. |

El JWT se obtiene **dentro del túnel VPN** (HTTP a `10.13.13.1:17017`), por lo que nunca viaja por internet en claro.

---

## Mecanismos de protección adicionales

### Anti-replay de nonces

Cada paquete knock incluye un nonce AES-GCM de 96 bits generado con `os.urandom()`. El servidor guarda todos los nonces vistos en la colección `vpn_nonces` de MongoDB con índice único y TTL. Si el mismo paquete se reenvía, el intento de insertar el nonce falla y el paquete se descarta silenciosamente.

```
nonce único → insert en vpn_nonces (TTL collection)
  ├─ OK        → procesamos el knock
  └─ Duplicate → descarte silencioso (replay attack)
```

### Validación de timestamp

El payload cifrado incluye el timestamp Unix del cliente. El servidor rechaza paquetes con más de ±30 segundos de desfase. Esto limita la ventana de ataque incluso si el nonce no estuviera protegido.

### Puerto oculto (port knocking pasivo)

El knock listener UDP no envía ninguna respuesta, ni siquiera para paquetes inválidos. Un escáner de puertos ve silencio; no puede distinguir entre un puerto cerrado y el knock listener. El servidor WireGuard (:51820) solo acepta handshakes de peers registrados, por lo que tampoco es explotable sin clave.

### Aislamiento entre clientes

Los peers WireGuard se registran con `AllowedIPs = <ip_del_cliente>/32`, no con la subred completa. Esto significa que el tráfico entre dos clientes VPN **no puede enrutarse por el servidor**; cada cliente solo puede alcanzar la IP del servidor (`10.13.13.1`). Un cliente comprometido no puede acceder a otros clientes VPN.

### Lease de onboarding (tiempo limitado)

Cuando el knock es válido, el servidor crea un lease con `state=onboarding` y expiración de 5 minutos. Si el cliente no completa la autenticación HTTP y el `POST /vpn/promote` en ese tiempo, el janitor limpia el peer y el lease automáticamente. Un atacante que capture un knock válido no puede usarlo indefinidamente.

### Autenticación HTTP dentro del túnel

El `POST /vpn/promote` requiere un JWT válido obtenido con usuario y contraseña. Esto añade un segundo factor humano: aunque un atacante tuviera el knock y el TOTP, necesitaría también las credenciales de la cuenta para completar el flujo.

---

## Modelo de amenazas y qué protege cada capa

| Amenaza | Capa de defensa |
|---|---|
| Escáner descubre el puerto de knock | Puerto silencioso — sin respuesta en ningún caso |
| Paquete de knock capturado y reenviado | Anti-replay de nonces + ventana de timestamp ±30 s |
| TOTP interceptado | TOTP de un solo uso + anti-replay; inútil pasados 30 s |
| Clave privada WireGuard robada del disco | No hay clave en disco: `/dev/shm` + borrado inmediato |
| Lectura de `/dev/shm/anc-vpn.conf` por otro proceso | Permisos `0600` + el fichero existe < 1 segundo |
| Cliente comprometido ve otros clientes VPN | `AllowedIPs = server_ip/32` — aislamiento estricto |
| Robo del JWT | Solo válido dentro del túnel (HTTP interno, no expuesto a internet) |
| Brecha en la base de datos (semilla TOTP) | Semilla cifrada con AES-256-GCM; sin la clave maestra del vault es inutilizable |
| SPA_PRIVKEY_B64 filtrada | Permite descifrar knocks futuros; no compromete sesiones pasadas (forward secrecy por clave efímera del cliente) |

---

## Resumen de dónde vive cada clave

```
SERVIDOR
  SPA_PRIVKEY_B64     → .env (disco del host, fuera del contenedor) + memoria del proceso
  WireGuard privkey   → /config dentro del contenedor wireguard (root only)
  JWT_SECRET          → .env + memoria del proceso
  TOTP seeds          → MongoDB, cifradas (AES-256-GCM + HKDF-SHA256)

CLIENTE
  WireGuard privkey   → /dev/shm/anc-vpn.conf (RAM, 0600, borrado < 1 s) → nunca en disco
  WireGuard pubkey    → generada en memoria, enviada en el knock cifrado
  TOTP app            → dispositivo del usuario (Google Authenticator, Authy, etc.)
  JWT                 → memoria del proceso + ~/.config/anchor/credentials.toml (0600)
  VPN config          → ~/.config/anchor/vpn.toml (0600) — sin claves privadas
```

La única información sensible persistida en el cliente es el JWT de sesión (revocable) y la configuración VPN sin claves privadas. Las claves criptográficas que protegen el túnel existen solo en RAM durante el tiempo que dura la conexión.

Lo que va cifrado (nadie puede leer):
  - Tu username (uid)
  - El código TOTP de 6 dígitos
  - Tu clave pública WireGuard
  - El timestamp

  Lo que va en claro / es observable:
  - source IP:port — metadato UDP/IP, inevitable
  - dest IP:port — el servidor y puerto de knock
  - Tamaño exacto del paquete: 186 bytes — fingerprint del protocolo
  - Los 4 bytes finales de versión: \x00\x02\x00\x00

  Un observador que conozca el protocolo SPA v2 puede detectar que ese
   paquete UDP de 186 bytes con ese sufijo es un knock de Anchor. No
  puede saber quién lo envía (dentro del payload) ni para qué usuario,
   pero sí puede inferir que alguien está intentando conectarse a una
  VPN con este sistema.

  La clave efímera es lo más importante para la privacidad: se genera
  nueva en cada knock (X25519PrivateKey.generate()), así que dos
  paquetes del mismo usuario son criptográficamente indistinguibles
  entre sí — no se pueden correlacionar aunque capturen el tráfico
  durante meses