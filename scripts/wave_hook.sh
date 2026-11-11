#!/usr/bin/env bash
# Hook de Claude Code para Wave Terminal: marca el bloque de la sesión que te necesita.
#
#   wave_hook.sh esperando    borde e insignia naranja (te necesita)
#   wave_hook.sh trabajando   quita la marca naranja, si la había
#   wave_hook.sh listo        quita el borde y deja una insignia verde (terminó)
#
# Wave quita las insignias solas cuando enfocas el bloque. Fuera de Wave no hace nada.
# Nunca falla, para no estorbarle a Claude Code.

cat >/dev/null 2>&1            # el evento que manda Claude Code no se usa aquí
# registro corto para revisar si el hook corre (las últimas 200 líneas)
REGISTRO="${TMPDIR:-/tmp}/starlight-wave.log"
{ echo "$(date '+%F %T') $1 bloque=${WAVETERM_BLOCKID:-ninguno}"; tail -n 199 "$REGISTRO" 2>/dev/null || true; } > "$REGISTRO.nuevo" 2>/dev/null \
  && mv -f "$REGISTRO.nuevo" "$REGISTRO" 2>/dev/null
[ -n "$WAVETERM_BLOCKID" ] || exit 0
WSH="$WAVETERM_WSHBINDIR/wsh"
[ -x "$WSH" ] || [ -x "$WSH.exe" ] || WSH="wsh"
MARCA="${TMPDIR:-/tmp}/starlight-wave-$WAVETERM_BLOCKID"
NARANJA="#ff6a1f"
VERDE="#3f8f4f"

{
  case "$1" in
    esperando)
      "$WSH" setmeta "frame:bordercolor=$NARANJA" "frame:activebordercolor=$NARANJA"
      "$WSH" badge bell-exclamation --color "$NARANJA" --priority 20
      : > "$MARCA"
      ;;
    trabajando)
      [ -e "$MARCA" ] || exit 0  # sin marca no hay nada que quitar: así no corre wsh en cada herramienta
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
