#!/usr/bin/env python3
"""Bluetooth Dial-Up Networking + Serial Port для S570HD → ha217b.

Запуск на нетбуке:
  sudo python3 bluetooth/dun.py

WinCE часто пишет «port is not available», если выбран Hayes на COM1.
Нужен модем Bluetooth / виртуальный COM от Serial Port. Поэтому
регистрируем и DUN (0x1103), и Serial Port (0x1101).
"""

from __future__ import annotations

import os
import signal
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modem import LOCAL_IP, run_at_then_ppp  # noqa: E402

DUN_UUID = "00001103-0000-1000-8000-00805f9b34fb"
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
DUN_PATH = "/org/ha_panel/dun"
SPP_PATH = "/org/ha_panel/spp"
BT_NAME = os.environ.get("BT_NAME", "ha217b")
DUN_CHANNEL = int(os.environ.get("DUN_CHANNEL", "1"))
SPP_CHANNEL = int(os.environ.get("SPP_CHANNEL", "2"))

DUN_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
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
  <attribute id="0x0008">
    <uint8 value="0xff"/>
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
    <text value="ha217b modem"/>
  </attribute>
</record>
""" % DUN_CHANNEL

SPP_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <attribute id="0x0001">
    <sequence>
      <uuid value="0x1101"/>
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
        <uuid value="0x1101"/>
        <uint16 value="0x0100"/>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100">
    <text value="Serial Port"/>
  </attribute>
  <attribute id="0x0101">
    <text value="ha217b serial"/>
  </attribute>
</record>
""" % SPP_CHANNEL


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
        # Networking / telephony class — WinCE охотнее показывает модем.
        try:
            props.Set(
                "org.bluez.Adapter1",
                "Class",
                dbus.UInt32(0x020300),
            )
        except dbus.exceptions.DBusException:
            pass
    except dbus.exceptions.DBusException as error:
        log("Bluetooth-адаптер: %s" % error)
        return 1

    sessions = {"n": 0}
    lock = threading.Lock()

    def spawn_session(label: str, device, handle) -> None:
        with lock:
            sessions["n"] += 1
            sid = sessions["n"]

        def worker() -> None:
            log("[%s #%s] сессия от %s (fd=%s)" % (label, sid, device, handle))
            try:
                run_at_then_ppp(handle, lambda m: log("[%s #%s] %s" % (label, sid, m)))
            except Exception as error:
                log("[%s #%s] ошибка: %s" % (label, sid, error))
            finally:
                try:
                    os.close(handle)
                except OSError:
                    pass
                log("[%s #%s] закрыта" % (label, sid))

        threading.Thread(
            target=worker, name="%s-%s" % (label, sid), daemon=True
        ).start()

    def make_profile(path: str, label: str):
        class Profile(dbus.service.Object):
            def __init__(self) -> None:
                super().__init__(bus, path)

            @dbus.service.method(
                "org.bluez.Profile1", in_signature="", out_signature=""
            )
            def Release(self) -> None:
                log("%s Release" % label)

            @dbus.service.method(
                "org.bluez.Profile1", in_signature="", out_signature=""
            )
            def Cancel(self) -> None:
                log("%s Cancel" % label)

            @dbus.service.method(
                "org.bluez.Profile1", in_signature="oha{sv}", out_signature=""
            )
            def NewConnection(self, device, fd, properties) -> None:
                handle = fd.take()
                for key, value in properties.items():
                    log("%s prop %s=%s" % (label, key, value))
                spawn_session(label, device, handle)

            @dbus.service.method(
                "org.bluez.Profile1", in_signature="o", out_signature=""
            )
            def RequestDisconnection(self, device) -> None:
                log("%s disconnect %s" % (label, device))

        return Profile()

    dun_profile = make_profile(DUN_PATH, "DUN")
    spp_profile = make_profile(SPP_PATH, "SPP")
    manager = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1"
    )

    common = {
        "Role": "server",
        "RequireAuthentication": dbus.Boolean(False),
        "RequireAuthorization": dbus.Boolean(False),
    }
    try:
        manager.RegisterProfile(
            DUN_PATH,
            DUN_UUID,
            {
                **common,
                "Name": "Dial-up Networking",
                "Channel": dbus.UInt16(DUN_CHANNEL),
                "ServiceRecord": DUN_RECORD,
            },
        )
        manager.RegisterProfile(
            SPP_PATH,
            SPP_UUID,
            {
                **common,
                "Name": "Serial Port",
                "Channel": dbus.UInt16(SPP_CHANNEL),
                "ServiceRecord": SPP_RECORD,
            },
        )
    except dbus.exceptions.DBusException as error:
        log("RegisterProfile: %s" % error)
        return 1

    log("Служба дозвона запущена (DUN + Serial Port).")
    log("  Имя:     %s" % BT_NAME)
    log("  DUN:     RFCOMM %s" % DUN_CHANNEL)
    log("  Serial:  RFCOMM %s" % SPP_CHANNEL)
    log("  Адрес:   %s после CONNECT" % LOCAL_IP)
    log("")
    log("Важно для WinCE — «port is not available»:")
    log("  НЕ выбирайте Hayes compatible / COM1.")
    log("  Нужен пункт с Bluetooth / ha217b / Dial-up Networking.")
    log("  Если модема Bluetooth нет в списке:")
    log("    Bluetooth manager → ha217b → сервисы → Dial-up / Serial")
    log("    иногда там же назначают исходящий COM (COM6/COM8).")
    log("  Затем Make New Connection → этот модем/COM → *99#")
    log("")
    log("Остановка: Ctrl+C")

    mainloop = GLib.MainLoop()

    def stop(*_args) -> None:
        log("остановка…")
        for path in (DUN_PATH, SPP_PATH):
            try:
                manager.UnregisterProfile(path)
            except dbus.exceptions.DBusException:
                pass
        mainloop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    # keep refs
    _ = (dun_profile, spp_profile)
    mainloop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
