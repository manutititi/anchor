#!/usr/bin/env bash
# anchor/shell/anc.sh
#
# Source this file in ~/.bashrc or ~/.zshrc:
#   source ~/.anchors/shell/anc.sh
#
# Para anchors locales (cd) no se invoca Python en absoluto:
# el JSON se lee directamente en bash, haciendo el cd casi instantáneo.
# Python solo se arranca para tipos que lo necesitan (ssh, go, etc.).

anc() {
    local _known="login set pull push ls path secret go _type -h --help"

    # Bare anchor name: un solo argumento, sin guión, no es subcomando conocido
    if [[ $# -eq 1 ]] && [[ "$1" != -* ]] && [[ " $_known " != *" $1 "* ]]; then
        local _name="$1"
        local _data_dir="${ANCHOR_DIR:-$HOME/.anchors/data}"
        local _file="$_data_dir/${_name}.json"

        if [[ -f "$_file" ]]; then
            local _type _path

            # Leer type y path del JSON sin arrancar Python ni el CLI completo.
            # Prioridad: jq (nativo, rápido) → python3 -c (mínimo) → CLI completo
            if command -v jq &>/dev/null; then
                _type=$(jq -r '.type // ""' "$_file" 2>/dev/null)
                _path=$(jq -r '.path // ""' "$_file" 2>/dev/null)
            else
                # python3 -c: sin typer/rich/pydantic — arranca en ~30ms
                _type=$(python3 -c \
                    "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('type',''))" \
                    "$_file" 2>/dev/null)
                _path=$(python3 -c \
                    "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('path',''))" \
                    "$_file" 2>/dev/null)
            fi

            case "$_type" in
                local)
                    # Expandir ~ sin invocar Python
                    _path="${_path/#\~/$HOME}"
                    if [[ -d "$_path" ]]; then
                        cd "$_path" || return 1
                        return 0
                    else
                        echo "anc: path does not exist: $_path" >&2
                        return 1
                    fi
                    ;;
                ssh)
                    # SSH necesita Python (vault, agente) — arranque único
                    command anc go "$_name"
                    return $?
                    ;;
                "")
                    # Fichero existe pero no tiene type — dejar que Python lo gestione
                    command anc go "$_name"
                    return $?
                    ;;
                *)
                    # Tipo desconocido para el shell — delegar al CLI
                    command anc go "$_name"
                    return $?
                    ;;
            esac
        else
            # Fichero no encontrado localmente — dejar que el CLI emita el error
            command anc go "$_name"
            return $?
        fi
    fi

    # Todo lo demás pasa directamente al binario
    command anc "$@"
}
