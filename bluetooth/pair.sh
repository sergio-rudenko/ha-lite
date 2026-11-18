#!/bin/bash
# Сопряжение S570HD ↔ нетбук ha217b.
# Запускать НА нетбуке (192.168.8.139), не в облаке:
#   sudo bash bluetooth/pair.sh
set -euo pipefail

PIN="${PIN:-1234}"
BT_NAME="${BT_NAME:-ha217b}"
PIN_FILE="${PIN_FILE:-/tmp/ha-panel-bt-pin}"

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
  bluetoothctl system-alias "${BT_NAME}" >/dev/null || bluetoothctl system-alias "${BT_NAME}"
  bluetoothctl pairable on >/dev/null
  bluetoothctl discoverable on >/dev/null
  # Без таймаута, пока крутится этот скрипт.
  if [[ -f /etc/bluetooth/main.conf ]]; then
    if grep -q '^DiscoverableTimeout' /etc/bluetooth/main.conf; then
      sed -i 's/^DiscoverableTimeout.*/DiscoverableTimeout = 0/' /etc/bluetooth/main.conf
    elif grep -q '^\[General\]' /etc/bluetooth/main.conf; then
      sed -i '/^\[General\]/a DiscoverableTimeout = 0' /etc/bluetooth/main.conf
    fi
  fi
  # Старый WinCE часто не умеет SSP — только PIN.
  if command -v btmgmt >/dev/null 2>&1; then
    btmgmt ssp off >/dev/null 2>&1 || true
    btmgmt pairable on >/dev/null 2>&1 || true
    btmgmt discov on >/dev/null 2>&1 || true
    btmgmt connectable on >/dev/null 2>&1 || true
  fi
}

printf '%s\n' "${PIN}" >"${PIN_FILE}"
chmod 600 "${PIN_FILE}"

need_root
install_pkgs
adapter_ready
prepare_adapter

ADDR="$(bluetoothctl show | awk '/Controller/{print $2; exit}')"
echo
echo "Нетбук готов к сопряжению."
echo "  Имя:     ${BT_NAME}"
echo "  Адрес:   ${ADDR:-неизвестен}"
echo "  PIN:     ${PIN}"
echo
echo "На навигаторе S570HD:"
echo "  1. Bluetooth → поиск устройств"
echo "  2. Выбрать ${BT_NAME}"
echo "  3. Ввести PIN ${PIN}"
echo
echo "Оставьте это окно открытым, пока не спаритесь."
echo "Остановка: Ctrl+C"
echo

# Агент с фиксированным PIN для legacy-сопряжения WinCE.
exec bt-agent -c NoInputNoOutput -p "${PIN_FILE}"
