#!/usr/bin/env bash
# Vigilante de esperas de Claude Code.
#
# Cuando cancelas con Esc una pregunta o un permiso, Claude Code no avisa a ningún hook: ni Stop
# ni PostToolUse. Sin esto, el borde naranja de Wave y el «esperando» de la Starlight se quedan
# prendidos hasta tu siguiente mensaje.
#
# Este script mira el historial de la sesión (transcript_path). Claude Code escribe ahí tanto tu
# respuesta como la cancelación. Apenas aparece, quita el naranja de Wave y le avisa al servidor.
#
#   Como hook (en los eventos que esperan: PreToolUse AskUserQuestion|ExitPlanMode y
#   Notification permission_prompt|elicitation_dialog):
#       bash /ruta/a/starlight-hack/scripts/vigilante.sh
#   wave_hook.sh lo arranca solo al marcar «esperando»: si usas ese hook, no hace falta agregarlo.
#
# Vuelve enseguida; el vigilante sigue solo en segundo plano. Hay como mucho uno por sesión: uno
# nuevo reemplaza al anterior. Se rinde a las 3 horas. Nunca falla.
#
# Variable opcional: STARLIGHT_URL (por defecto http://127.0.0.1:8765).

DIR=${0%/*}; [ "$DIR" = "$0" ] && DIR=.
URL="${STARLIGHT_URL:-http://127.0.0.1:8765}"
TMP="${TMPDIR:-/tmp}"
ESPERA_MAX=10800   # 3 horas

if [ "$1" != "--vigilar" ]; then
  # Modo hook: leer el evento, soltar el vigilante y volver de inmediato (casi sin lanzar procesos).
  if [ -n "$1" ]; then          # wave_hook.sh ya leyó el evento y pasa los datos
    SID="$1"; HISTORIAL="$2"; HERRAMIENTA_ID="$3"
  else
    EVENTO=""
    IFS= read -r -d '' -N 16000 EVENTO 2>/dev/null
    [ ${#EVENTO} -ge 16000 ] && cat >/dev/null 2>&1
    leer() {  # leer <variable> <campo>: el valor de un campo de texto del evento, sin jq
      local re="\"$2\" *: *\"([^\"]*)\""
      if [[ $EVENTO =~ $re ]]; then printf -v "$1" '%s' "${BASH_REMATCH[1]}"; else printf -v "$1" ''; fi
    }
    leer SID session_id; leer HISTORIAL transcript_path; leer HERRAMIENTA_ID tool_use_id
  fi
  # En Windows el JSON trae C:\\Users\\...: bash lo abre mejor como C:/Users/...
  HISTORIAL=${HISTORIAL//\\\\//}
  HISTORIAL=${HISTORIAL//\\//}
  [ -n "$SID" ] && [ -f "$HISTORIAL" ] || exit 0
  # Suelto del hook: sin las salidas del hook y en su propia sesión si se puede, para que el
  # límite de tiempo del hook no lo mate.
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup bash "$0" --vigilar "$SID" "$HISTORIAL" "$HERRAMIENTA_ID" </dev/null >/dev/null 2>&1 &
  else
    nohup bash "$0" --vigilar "$SID" "$HISTORIAL" "$HERRAMIENTA_ID" </dev/null >/dev/null 2>&1 &
  fi
  exit 0
fi

# Modo vigilante (en segundo plano).
SID="$2"; HISTORIAL="$3"; HERRAMIENTA_ID="$4"
TURNO="$TMP/starlight-vigilante-$SID"
echo $$ > "$TURNO" 2>/dev/null || exit 0     # reemplaza a otro vigilante de la misma sesión
INICIO=$(wc -c < "$HISTORIAL" 2>/dev/null | tr -d ' ') || exit 0
TAMANO="$INICIO"
FIN=""
SEGUNDOS=0

while [ "$SEGUNDOS" -lt "$ESPERA_MAX" ]; do
  sleep 1
  SEGUNDOS=$((SEGUNDOS + 1))
  DUENO=""; read -r DUENO < "$TURNO" 2>/dev/null
  [ "$DUENO" = "$$" ] || exit 0   # llegó otro vigilante: él sigue
  [ -f "$HISTORIAL" ] || break
  AHORA=$(wc -c < "$HISTORIAL" 2>/dev/null | tr -d ' ')
  [ "$AHORA" = "$TAMANO" ] && continue
  TAMANO="$AHORA"
  NUEVO=$(tail -c +"$((INICIO + 1))" "$HISTORIAL" 2>/dev/null)
  # La espera terminó cuando llega el resultado de la herramienta que esperaba (tu respuesta,
  # tu permiso o tu «no») o el aviso de que interrumpiste.
  if [ -n "$HERRAMIENTA_ID" ]; then
    printf '%s' "$NUEVO" | grep '"type":"user"' | grep -q "$HERRAMIENTA_ID" && FIN=respondido
  else
    printf '%s' "$NUEVO" | grep '"type":"user"' | grep -q '"tool_result"' && FIN=respondido
  fi
  if printf '%s' "$NUEVO" | grep '"type":"user"' | grep -q 'Request interrupted by user'; then
    FIN=interrumpido
  elif [ -n "$FIN" ]; then
    # tras un rechazo, Claude Code escribe el aviso de interrupción justo después: darle un momento
    sleep 1
    tail -c +"$((INICIO + 1))" "$HISTORIAL" 2>/dev/null | grep '"type":"user"' \
      | grep -q 'Request interrupted by user' && FIN=interrumpido
  fi
  [ -n "$FIN" ] && break
done

DUENO=""; read -r DUENO < "$TURNO" 2>/dev/null
[ "$DUENO" = "$$" ] && rm -f "$TURNO"
[ -n "$FIN" ] || exit 0

# Avisar a Wave (si la sesión corre en Wave) y al servidor de la Starlight.
bash "$DIR/wave_hook.sh" fin </dev/null >/dev/null 2>&1
curl -s -m 2 -X POST -H 'Content-Type: application/json' -H "X-Orden: $(date +%s%N)" \
  --data-binary "{\"session_id\":\"$SID\",\"hook_event_name\":\"FinEspera\",\"fin\":\"$FIN\"}" \
  "$URL/api/claude/hook" >/dev/null 2>&1
exit 0
