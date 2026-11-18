#!/usr/bin/env python3
"""Bluetooth Dial-Up Networking для S570HD → нетбук ha217b.

Запуск на нетбуке:
  sudo python3 bluetooth/dun.py

Пока скрипт работает, навигатор в Make New Connection видит ha217b как модем.
"""

from __future__ import annotations

import os
import signal
import sys
import threading

# Каталог bluetooth/ рядом с этим файлом.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modem import LOCAL_IP, run_at_then_ppp  # noqa: E402

DUN_UUID = "00001103-0000-1000-8000-00805f9b34fb"
PROFILE_PATH = "/org/ha_panel/dun"
BT_NAME = os.environ.get("BT_NAME", "ha217b")
CHANNEL = int(os.environ.get("DUN_CHANNEL", "3"))

# SDP: Dial-up Networking на RFCOMM.
SERVICE_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <attribute id="0x0001">
    <sequence>
      <uuid value="0x1103"/>
    </sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence>
        <uuid value="0x0100"/>
      </sequence>
      <sequence>
        <uuid value="0x0003"/>
        <uint8 value="%d"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence>
      <sequence>
        <uuid value="0x1103"/>
        <uint16 value="0x0100"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100">
    <text value="Dial-up Networking"/>
  </attribute>
  <attribute id="0x0101">
    <text value="ha217b"/>
  </attribute>
</record>
""" % CHANNEL


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> int:
    if os.geteuid() != 0:
        log("Запустите от root: sudo python3 bluetooth/dun.py")
        return 1

    try:
        import dbus
        import dbus.mainloop.glib
        import dbus.service
        from gi.repository import GLib
    except ImportError:
        log("Нужны пакеты: sudo apt install python3-dbus python3-gi bluez ppp")
        return 1

    from modem import pppd_bin

    if pppd_bin() is None:
        log("Не найден pppd. Установите: sudo apt install ppp")
        return 1

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    try:
        adapter = bus.get_object("org.bluez", "/org/bluez/hci0")
        props = dbus.Interface(adapter, "org.freedesktop.DBus.Properties")
        props.Set("org.bluez.Adapter1", "Powered", dbus.Boolean(True))
        props.Set("org.bluez.Adapter1", "Alias", BT_NAME)
        props.Set("org.bluez.Adapter1", "Discoverable", dbus.Boolean(True))
        props.Set("org.bluez.Adapter1", "Pairable", dbus.Boolean(True))
    except dbus.exceptions.DBusException as error:
        log("Bluetooth-адаптер: %s" % error)
        return 1

    class DunProfile(dbus.service.Object):
        def __init__(self) -> None:
            super().__init__(bus, PROFILE_PATH)
            self._lock = threading.Lock()

        @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
        def Release(self) -> None:
            log("Release")
            mainloop.quit()

        @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
        def Cancel(self) -> None:
            log("Cancel")

        @dbus.service.method(
            "org.bluez.Profile1", in_signature="oha{sv}", out_signature=""
        )
        def NewConnection(self, device, fd, properties) -> None:
            handle = fd.take()
            log("входящий дозвон от %s (fd=%s)" % (device, handle))
            for key, value in properties.items():
                log("  %s=%s" % (key, value))

            def worker() -> None:
                try:
                    run_at_then_ppp(handle, log)
                except Exception as error:
                    log("ошибка сессии: %s" % error)
                finally:
                    try:
                        os.close(handle)
                    except OSError:
                        pass
                    log("сессия закрыта")

            threading.Thread(target=worker, name="dun-session", daemon=True).start()

        @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
        def RequestDisconnection(self, device) -> None:
            log("отключение %s" % device)

    profile = DunProfile()
    manager = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1"
    )
    opts = {
        "Name": "Dial-up Networking",
        "Role": "server",
        "Channel": dbus.UInt16(CHANNEL),
        "RequireAuthentication": dbus.Boolean(True),
        "RequireAuthorization": dbus.Boolean(False),
        "ServiceRecord": SERVICE_RECORD,
    }
    try:
        manager.RegisterProfile(PROFILE_PATH, DUN_UUID, opts)
    except dbus.exceptions.DBusException as error:
        log("RegisterProfile: %s" % error)
        return 1

    log("Служба дозвона запущена.")
    log("  Имя:    %s" % BT_NAME)
    log("  UUID:   Dial-up Networking")
    log("  Канал:  RFCOMM %s" % CHANNEL)
    log("  Адрес:  %s (после CONNECT)" % LOCAL_IP)
    log("")
    log("На навигаторе:")
    log("  1. Панель управления → Make New Connection")
    log("  2. Выбрать сопряжённый %s" % BT_NAME)
    log("  3. Тип: Dial-Up / модем Bluetooth")
    log("  4. Номер *99# , имя и пароль пустые")
    log("  5. Подключить → браузер http://%s:4731/" % LOCAL_IP)
    log("")
    log("Остановка: Ctrl+C")

    mainloop = GLib.MainLoop()

    def stop(*_args) -> None:
        log("остановка…")
        try:
            manager.UnregisterProfile(PROFILE_PATH)
        except dbus.exceptions.DBusException:
            pass
        mainloop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    mainloop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
