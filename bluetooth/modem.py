"""AT-ответы дозвона Windows CE и двусторонний мост в pppd."""

from __future__ import annotations

import os
import pty
import select
import shutil
import subprocess
import threading
from typing import Callable

PPP_FLAG = 0x7E
LOCAL_IP = "10.44.0.1"
REMOTE_IP = "10.44.0.2"


class AtModem:
    """Принимает AT-команды и отделяет их от кадров PPP.

    Навигатор шлёт AT и номер *99#, после CONNECT начинается PPP.
    Иногда кадр PPP приходит в том же чтении, что и ATD.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.finished = False
        self.hungup = False
        self.ppp = bytearray()

    def feed(self, data: bytes) -> bytes:
        if self.finished:
            self.ppp.extend(data)
            return b""
        self._buf.extend(data)
        out = bytearray()
        while True:
            if self.finished:
                self.ppp.extend(self._buf)
                self._buf.clear()
                break
            flag = self._buf.find(PPP_FLAG)
            eol = _eol(self._buf)
            if flag != -1 and (eol is None or flag < eol):
                head = bytearray(self._buf[:flag])
                self.ppp.extend(self._buf[flag:])
                self._buf.clear()
                self.finished = True
                out.extend(_commands(self, head))
                break
            line = _pop_line(self._buf)
            if line is None:
                break
            out.extend(self._command(line))
        return bytes(out)

    def _command(self, line: bytes) -> bytes:
        text = line.decode("ascii", "replace").strip()
        if not text:
            return b""
        upper = text.upper()
        if not upper.startswith("AT"):
            return b""
        body = upper[2:].lstrip()
        if body.startswith("D"):
            self.finished = True
            return b"CONNECT\r\n"
        if body.startswith("H"):
            self.hungup = True
            self.finished = True
            return b"OK\r\n"
        return b"OK\r\n"


def _eol(buf: bytearray) -> int | None:
    for i, byte in enumerate(buf):
        if byte in (10, 13):
            return i
    return None


def _pop_line(buf: bytearray) -> bytes | None:
    eol = _eol(buf)
    if eol is None:
        return None
    line = bytes(buf[:eol])
    end = eol
    while end < len(buf) and buf[end] in (10, 13):
        end += 1
    del buf[:end]
    return line


def _commands(modem: AtModem, buf: bytearray) -> bytes:
    out = bytearray()
    while True:
        line = _pop_line(buf)
        if line is None:
            break
        out.extend(modem._command(line))
        if modem.finished:
            break
    return bytes(out)


def pppd_bin() -> str | None:
    found = shutil.which("pppd")
    if found:
        return found
    for path in ("/usr/sbin/pppd", "/sbin/pppd"):
        if os.access(path, os.X_OK):
            return path
    return None


def pppd_args(device: str) -> list[str]:
    binary = pppd_bin()
    if binary is None:
        raise RuntimeError("Не найден pppd. На нетбуке: sudo apt install ppp")
    return [
        binary,
        device,
        "115200",
        "nodetach",
        "local",
        "nocrtscts",
        "passive",
        "novj",
        "novjccomp",
        "nobsdcomp",
        "nodeflate",
        "noccp",
        "nopcomp",
        "noaccomp",
        "nomagic",
        "asyncmap",
        "0",
        "mtu",
        "512",
        "mru",
        "512",
        "lcp-echo-interval",
        "30",
        "lcp-echo-failure",
        "4",
        "lcp-max-configure",
        "30",
        "ms-dns",
        LOCAL_IP,
        "%s:%s" % (LOCAL_IP, REMOTE_IP),
        "noauth",
    ]


def run_at_then_ppp(fd: int, log: Callable[[str], None]) -> None:
    """На fd: сначала AT-модем, затем PPP через pty.

    BlueZ часто отдаёт неблокирующий сокет: os.read сразу даёт EAGAIN (11),
    это не обрыв — ждём данные через select.
    """
    try:
        os.set_blocking(fd, True)
    except OSError:
        pass

    modem = AtModem()
    while not modem.finished:
        try:
            readable, _, _ = select.select([fd], [], [], 60.0)
        except (OSError, ValueError) as error:
            log("обрыв на AT (select): %s" % error)
            return
        if not readable:
            log("ждём AT-команды от навигатора…")
            continue
        try:
            chunk = os.read(fd, 2048)
        except BlockingIOError:
            continue
        except OSError as error:
            # 11 = EAGAIN на старых ядрах / если fd снова non-blocking
            if error.errno in (11, getattr(__import__("errno"), "EAGAIN", 11)):
                try:
                    os.set_blocking(fd, True)
                except OSError:
                    pass
                continue
            log("обрыв на AT: %s" % error)
            return
        if not chunk:
            log("канал закрыт на этапе AT")
            return
        log("AT << %r" % chunk[:120])
        reply = modem.feed(chunk)
        if reply:
            log("AT >> %r" % reply)
            try:
                os.write(fd, reply)
            except OSError as error:
                log("запись AT: %s" % error)
                return
        if modem.hungup:
            log("навигатор положил трубку")
            return

    backlog = bytes(modem.ppp)
    if backlog:
        log("уже есть %d байт PPP" % len(backlog))
    start_pppd(fd, backlog, log)


def start_pppd(fd: int, backlog: bytes, log: Callable[[str], None]) -> None:
    """Двусторонний мост Bluetooth fd ↔ pty ↔ pppd."""
    master, slave = pty.openpty()
    slave_name = os.ttyname(slave)
    cmd = pppd_args(slave_name)
    log("запуск: %s" % " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(slave)

    def follow() -> None:
        stream = proc.stdout
        if stream is None:
            return
        for raw in stream:
            line = raw.decode("utf-8", "replace").rstrip()
            log("pppd: %s" % line)
            if "IP address" in line or "local  IP address" in line:
                log("Канал поднят. На навигаторе: http://%s:4731/" % LOCAL_IP)
        code = proc.wait()
        log("pppd завершился с кодом %s" % code)

    threading.Thread(target=follow, name="ppp-log", daemon=True).start()

    try:
        if backlog:
            os.write(master, backlog)
        _bridge(fd, master, log)
    finally:
        try:
            os.close(master)
        except OSError:
            pass
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()


def _bridge(fd: int, master: int, log: Callable[[str], None]) -> None:
    for handle in (fd, master):
        os.set_blocking(handle, False)
    try:
        while True:
            readable, _, _ = select.select([fd, master], [], [], 60.0)
            if not readable:
                log("тишина 60 с, ждём дальше")
                continue
            if fd in readable:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    data = b""
                except OSError as error:
                    log("чтение BT: %s" % error)
                    break
                if not data:
                    log("BT закрыл канал")
                    break
                os.write(master, data)
            if master in readable:
                try:
                    data = os.read(master, 4096)
                except BlockingIOError:
                    data = b""
                except OSError as error:
                    log("чтение pty: %s" % error)
                    break
                if not data:
                    log("pppd закрыл pty")
                    break
                os.write(fd, data)
    finally:
        for handle in (fd, master):
            try:
                os.set_blocking(handle, True)
            except OSError:
                pass
