#!/usr/bin/env bash
# Hook de Claude Code para Wave Terminal: marca el bloque de la sesión que te necesita.
#
#   wave_hook.sh esperando    borde e insignia naranja (te necesita) y arranca vigilante.sh
#   wave_hook.sh trabajando   quita la marca naranja, si la había
#   wave_hook.sh listo        quita el borde y deja una insignia verde (terminó)
#   wave_hook.sh fin          lo usa vigilante.sh: la espera terminó (respondiste o cancelaste)
#
# Si cancelas con Esc, Claude Code no avisa a ningún hook; vigilante.sh lo detecta en el historial
# de la sesión y quita el naranja (también avisa al servidor de la Starlight).
#
# Wave quita las insignias solas cuando enfocas el bloque. Fuera de Wave solo arranca el vigilante.
# Nunca falla, para no estorbarle a Claude Code. Corre en cada herramienta, así que casi no lanza
# procesos (en Git Bash, en Windows, cada uno cuesta).

DIR=${0%/*}; [ "$DIR" = "$0" ] && DIR=.
EVENTO=""
IFS= read -r -d '' -N 16000 EVENTO 2>/dev/null
[ ${#EVENTO} -ge 16000 ] && cat >/dev/null 2>&1   # el resto del evento no se usa
leer() {  # leer <variable> <campo>: el valor de un campo de texto del evento, sin jq ni procesos
  local re="\"$2\" *: *\"([^\"]*)\""
  if [[ $EVENTO =~ $re ]]; then printf -v "$1" '%s' "${BASH_REMATCH[1]}"; else printf -v "$1" ''; fi
}
leer NOMBRE hook_event_name

# registro corto para revisar si el hook corre (la línea más nueva al final; se recorta a 200)
REGISTRO="${TMPDIR:-/tmp}/starlight-wave.log"
printf -v AHORA '%(%F %T)T' -1
echo "$AHORA $1 evento=${NOMBRE:-ninguno} bloque=${WAVETERM_BLOCKID:-ninguno}" >> "$REGISTRO" 2>/dev/null
if (( RANDOM % 40 == 0 )); then
  tail -n 200 "$REGISTRO" > "$REGISTRO.$$" 2>/dev/null && mv -f "$REGISTRO.$$" "$REGISTRO" 2>/dev/null
fi

leer SID session_id
if [ "$1" = "esperando" ]; then
  leer HISTORIAL transcript_path; leer HERRAMIENTA_ID tool_use_id
  bash "$DIR/vigilante.sh" "$SID" "$HISTORIAL" "$HERRAMIENTA_ID" </dev/null >/dev/null 2>&1
fi

# Decirle al servidor de la Starlight en qué bloque de Wave corre esta sesión, para que un pad pueda
# llevarte a ella. El servidor lo guarda en disco; igual se repite en cada mensaje tuyo, al final de
# cada turno y cuando te espera, por si el servidor lo perdió.
if [ -n "$WAVETERM_BLOCKID" ] && [ -n "$SID" ]; then
  AVISADO="${TMPDIR:-/tmp}/starlight-bloque-$SID"
  YA=""; read -r YA < "$AVISADO" 2>/dev/null
  if [ "$YA" != "$WAVETERM_BLOCKID" ] || [ "$NOMBRE" = "UserPromptSubmit" ] || [ "$NOMBRE" = "Stop" ] \
     || [ "$1" = "esperando" ]; then
    echo "$WAVETERM_BLOCKID" > "$AVISADO" 2>/dev/null
    curl -s -m 2 -X POST -H 'Content-Type: application/json' \
      --data-binary "{\"session_id\":\"$SID\",\"hook_event_name\":\"Bloque\",\"bloque\":\"$WAVETERM_BLOCKID\"}" \
      "${STARLIGHT_URL:-http://127.0.0.1:8765}/api/claude/hook" >/dev/null 2>&1
  fi
fi

[ -n "$WAVETERM_BLOCKID" ] || exit 0
MARCA="${TMPDIR:-/tmp}/starlight-wave-$WAVETERM_BLOCKID"
# sin marca no hay nada que quitar: así no corre wsh en cada herramienta
case "$1" in trabajando|fin) [ -e "$MARCA" ] || exit 0 ;; esac
WSH="$WAVETERM_WSHBINDIR/wsh"
[ -x "$WSH" ] || [ -x "$WSH.exe" ] || WSH="wsh"
NARANJA="#ff6a1f"
VERDE="#3f8f4f"

{
  case "$1" in
    esperando)
      "$WSH" setmeta "frame:bordercolor=$NARANJA" "frame:activebordercolor=$NARANJA"
      "$WSH" badge bell-exclamation --color "$NARANJA" --priority 20
      : > "$MARCA"
      ;;
    trabajando|fin)
      "$WSH" setmeta frame:bordercolor=null frame:activebordercolor=null
      "$WSH" badge --clear
      rm -f "$MARCA"
      ;;
    listo)
      "$WSH" setmeta frame:bordercolor=null frame:activebordercolor=null
      "$WSH" badge circle-check --color "$VERDE" --priority 5
      rm -f "$MARCA"
      ;;
  esac
} >/dev/null 2>&1
exit 0
