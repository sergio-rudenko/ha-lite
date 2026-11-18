#!/usr/bin/env python3
"""Bluetooth DUN + Serial Port для S570HD → ha217b.

Если WinCE пишет «port is not available», а этот скрипт молчит —
RFCOMM до нетбука даже не доходит. Сначала в Bluetooth-менеджере
навигатора сделайте Connect к Dial-up Networking / ha217b, и только
потом Connect в Remote Networking. Здесь должны появиться строки сессии.

  sudo python3 bluetooth/dun.py
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
AGENT_PATH = "/org/ha_panel/agent"
BT_NAME = os.environ.get("BT_NAME", "ha217b")
DUN_CHANNEL = int(os.environ.get("DUN_CHANNEL", "1"))
SPP_CHANNEL = int(os.environ.get("SPP_CHANNEL", "2"))

# 0x1103 DUN + 0x1201 Networking — так старые стеки чаще видят «модем».
DUN_RECORD = """<?xml version="1.0" encoding="UTF-8"?>
<record>
  <attribute id="0x0001">
    <sequence>
      <uuid value="0x1103"/>
      <uuid value="0x1201"/>
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
        try:
            props.Set("org.bluez.Adapter1", "DiscoverableTimeout", dbus.UInt32(0))
        except dbus.exceptions.DBusException:
            pass
        adapter_addr = str(props.Get("org.bluez.Adapter1", "Address"))
    except dbus.exceptions.DBusException as error:
        log("Bluetooth-адаптер: %s" % error)
        return 1

    # Trust всем уже спаренным — иначе входящий RFCOMM режется молча.
    obj_manager = dbus.Interface(
        bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager"
    )
    paired = []
    for path, interfaces in obj_manager.GetManagedObjects().items():
        if "org.bluez.Device1" not in interfaces:
            continue
        dev = interfaces["org.bluez.Device1"]
        name = str(dev.get("Name") or dev.get("Alias") or "?")
        addr = str(dev.get("Address"))
        is_paired = bool(dev.get("Paired", False))
        if not is_paired:
            continue
        paired.append((addr, name, str(path)))
        try:
            device = bus.get_object("org.bluez", path)
            dbus.Interface(device, "org.freedesktop.DBus.Properties").Set(
                "org.bluez.Device1", "Trusted", dbus.Boolean(True)
            )
            log("trusted: %s (%s)" % (addr, name))
        except dbus.exceptions.DBusException as error:
            log("trust %s: %s" % (addr, error))

    if not paired:
        log("Пока нет спаренных устройств. Сначала pair.sh / сопряжение с навигатором.")

    class Agent(dbus.service.Object):
        @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
        def Release(self) -> None:
            pass

        @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
        def AuthorizeService(self, device, uuid) -> None:
            log("AuthorizeService %s %s" % (device, uuid))

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
        def RequestPinCode(self, device) -> str:
            log("RequestPinCode %s → 1234" % device)
            return "1234"

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
        def RequestPasskey(self, device) -> int:
            return dbus.UInt32(1234)

        @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
        def DisplayPasskey(self, device, passkey, entered) -> None:
            log("DisplayPasskey %s %s" % (device, passkey))

        @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
        def DisplayPinCode(self, device, pincode) -> None:
            log("DisplayPinCode %s %s" % (device, pincode))

        @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
        def RequestConfirmation(self, device, passkey) -> None:
            log("RequestConfirmation %s %s — ok" % (device, passkey))

        @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
        def RequestAuthorization(self, device) -> None:
            log("RequestAuthorization %s — ok" % device)

        @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
        def Cancel(self) -> None:
            pass

    agent = Agent(bus, AGENT_PATH)
    agent_mgr = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1"
    )
    try:
        agent_mgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
        agent_mgr.RequestDefaultAgent(AGENT_PATH)
        log("agent: NoInputNoOutput (auto-accept)")
    except dbus.exceptions.DBusException as error:
        log("agent: %s (продолжаем без него)" % error)

    sessions = {"n": 0}
    lock = threading.Lock()

    def spawn_session(label: str, device, handle) -> None:
        with lock:
            sessions["n"] += 1
            sid = sessions["n"]

        def worker() -> None:
            log("[%s #%s] ★ входящий RFCOMM от %s (fd=%s)" % (label, sid, device, handle))
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

    log("")
    log("Служба готова.")
    log("  Адаптер: %s (%s)" % (BT_NAME, adapter_addr))
    log("  DUN RFCOMM %s + Serial RFCOMM %s" % (DUN_CHANNEL, SPP_CHANNEL))
    log("  После CONNECT панель: http://%s:4731/" % LOCAL_IP)
    log("")
    log("Навигатор (GPS system) — клиент DUN. Исходящий Connect с нетбука")
    log("к нему даёт br-connection-profile-unavailable — это нормально,")
    log("линк должен открыть сам WinCE при наборе номера.")
    log("")
    log("=== S570HD (только trusted/untrusted) ===")
    log("1. В trusted только эта пара (GPS system / ha217b). Лишние удалите.")
    log("2. Remote Networking → Bluetooth DUN modem или DUN on COM8 → *99#")
    log("3. Не Hayes on COM1.")
    log("4. Успех здесь = строка «★ входящий RFCOMM».")
    log("")
    log("Жду входящий RFCOMM от навигатора. Остановка: Ctrl+C")

    mainloop = GLib.MainLoop()

    def status_paired() -> bool:
        try:
            objects = obj_manager.GetManagedObjects()
        except dbus.exceptions.DBusException:
            return True
        for path, interfaces in objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            dev = interfaces["org.bluez.Device1"]
            if not bool(dev.get("Paired", False)):
                continue
            addr = str(dev.get("Address"))
            name = str(dev.get("Name") or dev.get("Alias") or "?")
            connected = bool(dev.get("Connected", False))
            log(
                "peer %s (%s) connected=%s trusted=%s"
                % (addr, name, connected, bool(dev.get("Trusted", False)))
            )
        return True

    status_paired()
    GLib.timeout_add_seconds(30, status_paired)

    def stop(*_args) -> None:
        log("остановка…")
        for path in (DUN_PATH, SPP_PATH):
            try:
                manager.UnregisterProfile(path)
            except dbus.exceptions.DBusException:
                pass
        try:
            agent_mgr.UnregisterAgent(AGENT_PATH)
        except dbus.exceptions.DBusException:
            pass
        mainloop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    _ = (dun_profile, spp_profile, agent)
    mainloop.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
