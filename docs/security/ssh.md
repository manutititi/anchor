# Seguridad en conexiones SSH

## El problema

El flujo tradicional de SSH almacena la clave privada en disco (`~/.ssh/id_rsa`, `~/.ssh/id_ed25519`, etc.). Esto crea varios vectores de riesgo:

- Cualquier proceso con acceso al sistema de ficheros puede leer la clave.
- Los backups o snapshots del disco incluyen la clave sin cifrado adicional.
- Una brecha en un equipo de desarrollador expone todas las infraestructuras a las que esa clave tiene acceso.

En entornos de equipo, compartir claves por email, Slack o repositorios es práctica habitual y extremadamente peligrosa.

## La solución: vault + ssh-agent temporal

Anchor resuelve esto en dos capas:

### Capa 1 — almacenamiento cifrado en el vault

La clave privada nunca se guarda en el anchor directamente. En su lugar se almacena una referencia:

```json
{
  "type": "ssh",
  "host": "mi-servidor.com",
  "user": "manu",
  "key": "[[secret:anc-server/private-key]]"
}
```

El marcador `[[secret:anc-server/private-key]]` apunta a un secreto en el vault del servidor, cifrado con AES-256-GCM + HKDF-SHA256. La clave privada real nunca toca el disco del cliente.

### Capa 2 — inyección en memoria con ssh-agent efímero

Cuando el usuario ejecuta `anc mi-servidor`, el flujo es:

```
1. Anchor llama a GET /vault/anc-server/private-key
        ↓
2. El servidor desencripta y devuelve el PEM por HTTPS
        ↓
3. Anchor lanza un ssh-agent temporal con socket propio
   ssh-agent -a /tmp/anc-XXXX/agent.sock
        ↓
4. Anchor carga la clave en el agente vía stdin (pipe, nunca fichero)
   ssh-add - < [PEM en memoria]
        ↓
5. Anchor ejecuta el cliente ssh nativo apuntando al agente temporal
   SSH_AUTH_SOCK=/tmp/anc-XXXX/agent.sock ssh -p 2222 manu@host
        ↓
6. Al terminar la sesión, se mata el agente (SIGTERM)
   La clave desaparece de RAM
```

## Propiedades de seguridad

| Propiedad | Detalle |
|-----------|---------|
| **Cero escrituras a disco** | La clave PEM existe únicamente como string Python y en el buffer del pipe hacia `ssh-add`. Nunca se escribe en `/tmp`, `/dev/shm` ni ningún fichero. |
| **Agente aislado** | Cada conexión crea un agente propio con socket en un directorio `0700`. No interfiere con el agente del sistema ni expone la clave a otras sesiones. |
| **Cliente nativo** | Se usa el binario `ssh` del sistema, no una reimplementación. Esto garantiza compatibilidad con `~/.ssh/config`, `known_hosts`, algoritmos actuales y futuras actualizaciones de seguridad de OpenSSH. |
| **Vida útil mínima** | El agente temporal existe solo durante la sesión SSH activa. Al desconectar, recibe `SIGTERM` y la clave desaparece de RAM. |
| **Control de acceso en el vault** | El servidor controla quién puede leer cada secreto mediante políticas por usuario y grupo. Un token expirado o revocado impide obtener la clave. |
| **Trazabilidad** | Cada GET al vault queda registrado en el log de auditoría del servidor con usuario, IP y timestamp. |

## Gestión de contraseñas SSH

Para anchors que usan contraseña en lugar de clave, el flujo es similar:

```
vault → contraseña en memoria → sshpass -d N → ssh
```

`sshpass -d N` lee la contraseña desde un file descriptor de pipe, no desde un argumento de línea de comandos. Esto evita que la contraseña aparezca en `/proc/<pid>/cmdline` y sea visible para otros procesos del sistema.

Si `sshpass` no está instalado, Anchor advierte al usuario y delega la autenticación al cliente ssh (que pedirá la contraseña interactivamente en el terminal).

## Riesgos residuales

Ningún sistema es completamente inmune. Los riesgos que permanecen son:

- **Swap no cifrado**: Si el sistema tiene swap activo y sin cifrar, el contenido de RAM (incluida la clave en tránsito) puede volcarse a disco bajo presión de memoria. Mitigación: cifrar el swap o usar `zram`.
- **Core dumps**: Un crash durante la sesión podría incluir la clave en el core dump. Mitigación: deshabilitar core dumps en producción (`ulimit -c 0`).
- **Root access**: Un atacante con root puede leer la RAM del proceso agente. Este riesgo es inherente a cualquier sistema que maneje secretos en memoria y no tiene solución a nivel de software.
- **Ventana de red**: La clave viaja del servidor al cliente por HTTPS. Un certificado comprometido o un ataque MitM activo podrían interceptarla. Mitigación: verificar el certificado del servidor Anchor, usar TLS con HSTS.

## Configuración de un anchor SSH seguro

```bash
# 1. Subir la clave privada al vault
anc secret push anc-server/private-key --file ~/.ssh/id_ed25519

# 2. Crear el anchor apuntando al secreto
anc set --ssh produccion manu@192.168.1.10:22 \
    --key-secret anc-server/private-key \
    --no-test

# 3. Conectar (la clave nunca toca el disco del cliente)
anc produccion
```

## Obtener la clave pública de un anchor

Para añadir la clave a `authorized_keys` en el servidor:

```bash
anc go produccion --pubkey
```

Imprime la clave pública derivada del secreto en el vault, lista para copiar al servidor.
