#!/bin/bash
# Сопряжение S570HD ↔ нетбук ha217b.
# Запускать НА нетбуке (192.168.8.139):
#   sudo bash bluetooth/pair.sh              # PIN 1234 (навигатор вводит с клавиатуры)
#   sudo bash bluetooth/pair.sh --just-works # без PIN
#   sudo bash bluetooth/pair.sh --to AA:BB:CC:DD:EE:FF
#       # пару начинает нетбук; PIN подставляет агент
set -euo pipefail

PIN="${PIN:-1234}"
BT_NAME="${BT_NAME:-ha217b}"
PIN_FILE="${PIN_FILE:-/tmp/ha-panel-bt-pin}"
MODE="pin"
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pin) MODE="pin"; shift ;;
    --just-works|--justworks) MODE="justworks"; shift ;;
    --to)
      MODE="initiate"
      TARGET="${2:-}"
      if [[ -z "${TARGET}" ]]; then
        echo "Укажите адрес навигатора: --to AA:BB:CC:DD:EE:FF" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "Неизвестный аргумент: $1" >&2
      exit 1
      ;;
  esac
done

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "Запустите от root: sudo bash $0" >&2
    exit 1
  fi
}

install_pkgs() {
  export DEBIAN_FRONTEND=noninteractive
  if ! command -v bluetoothctl >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y bluez
  fi
  if ! command -v bt-agent >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y bluez-tools
  fi
}

adapter_ready() {
  systemctl enable --now bluetooth >/dev/null 2>&1 || true
  sleep 1
  if ! bluetoothctl show >/dev/null 2>&1; then
    echo "Адаптер Bluetooth не найден. Проверьте встроенный модуль нетбука." >&2
    exit 1
  fi
}

prepare_adapter() {
  bluetoothctl power on >/dev/null
  bluetoothctl system-alias "${BT_NAME}" >/dev/null || true
  bluetoothctl pairable on >/dev/null
  bluetoothctl discoverable on >/dev/null
  if command -v btmgmt >/dev/null 2>&1; then
    if [[ "${MODE}" == "justworks" ]]; then
      btmgmt ssp on >/dev/null 2>&1 || true
    else
      # Старый WinCE с полем PIN часто ждёт legacy-пару.
      btmgmt ssp off >/dev/null 2>&1 || true
    fi
    btmgmt pairable on >/dev/null 2>&1 || true
    btmgmt discov on >/dev/null 2>&1 || true
    btmgmt connectable on >/dev/null 2>&1 || true
  fi
}

print_wince_keyboard_hint() {
  cat <<'EOF'

Если на навигаторе снова попросят PIN и нет клавиатуры:
  • ткните в поле PIN — иногда всплывает цифровая панель;
  • иконка клавиатуры внизу экрана / в трее WinCE;
  • в проводнике найдите и запустите ToggleInputPanel.exe
    (часто лежит в ResidentFlash2 или на карте);
  • либо прервите и используйте режим без PIN (скрипт по умолчанию)
    или пару с нетбука: sudo bash pair.sh --to <адрес навигатора>

EOF
}

need_root
install_pkgs
adapter_ready
prepare_adapter

ADDR="$(bluetoothctl show | awk '/Controller/{print $2; exit}')"
echo
echo "Адаптер: ${BT_NAME} (${ADDR:-?})"
echo "Режим:   ${MODE}"

if [[ "${MODE}" == "justworks" ]]; then
  echo "PIN не нужен. На навигаторе выберите ${BT_NAME} и подтвердите пару без ввода."
  print_wince_keyboard_hint
  echo "Оставьте окно открытым. Остановка: Ctrl+C"
  echo
  exec bt-agent -c NoInputNoOutput
fi

printf '%s\n' "${PIN}" >"${PIN_FILE}"
chmod 600 "${PIN_FILE}"

if [[ "${MODE}" == "pin" ]]; then
  echo "PIN: ${PIN}"
  echo "На навигаторе нужна клавиатура или цифровая панель."
  print_wince_keyboard_hint
  echo "Оставьте окно открытым. Остановка: Ctrl+C"
  echo
  exec bt-agent -c NoInputNoOutput -p "${PIN_FILE}"
fi

# MODE=initiate — пару начинает нетбук, PIN отдаёт агент.
echo "Цель: ${TARGET}"
echo "Сканирование 12 с…"
bluetoothctl --timeout 12 scan on >/dev/null 2>&1 || true
bt-agent -c NoInputNoOutput -p "${PIN_FILE}" &
AGENT_PID=$!
trap 'kill ${AGENT_PID} 2>/dev/null || true' EXIT
sleep 1
echo "Запрос пары к ${TARGET} (PIN ${PIN} подставит нетбук)…"
if bluetoothctl pair "${TARGET}"; then
  bluetoothctl trust "${TARGET}" || true
  echo
  echo "Готово. Проверьте на навигаторе, что ${BT_NAME} в списке paired."
else
  echo
  echo "Пара не установилась. Убедитесь, что навигатор виден по Bluetooth и близко."
  print_wince_keyboard_hint
  exit 1
fi
