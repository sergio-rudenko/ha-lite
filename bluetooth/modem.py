"""AT-ответы дозвона Windows CE и запуск pppd на уже открытом канале."""

import os
import shutil
import subprocess
import threading

PPP_FLAG = 0x7E
LOCAL_IP = "10.44.0.1"
REMOTE_IP = "10.44.0.2"


class AtModem:
    """Принимает команды модема и отделяет их от кадров PPP.

    Навигатор сначала шлёт AT-команды и номер *99#, и только после ответа
    CONNECT начинает PPP. Иногда кадр PPP приходит в том же чтении, что и ATD.
    """

    def __init__(self):
        self._buf = bytearray()
        self.finished = False
        self.hungup = False
        self.ppp = bytearray()

    def feed(self, data):
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

    def _command(self, line):
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


def _eol(buf):
    for i, byte in enumerate(buf):
        if byte in (10, 13):
            return i
    return None


def _pop_line(buf):
    eol = _eol(buf)
    if eol is None:
        return None
    line = bytes(buf[:eol])
    end = eol
    while end < len(buf) and buf[end] in (10, 13):
        end += 1
    del buf[:end]
    return line


def _commands(modem, buf):
    out = bytearray()
    while True:
        line = _pop_line(buf)
        if line is None:
            break
        out.extend(modem._command(line))
        if modem.finished:
            break
    return bytes(out)


def pppd_bin():
    found = shutil.which("pppd")
    if found:
        return found
    for path in ("/usr/sbin/pppd", "/sbin/pppd"):
        if os.access(path, os.X_OK):
            return path
    return None


def pppd_command():
    binary = pppd_bin() or "pppd"
    return [
        binary,
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


def start_pppd(sock, backlog, log):
    """Отдаёт pppd сначала уже прочитанные байты, затем остальной канал."""
    binary = pppd_bin()
    if binary is None:
        raise RuntimeError("Не найден pppd. На нетбуке: sudo apt install ppp")
    read_fd, write_fd = os.pipe()
    proc = subprocess.Popen(
        pppd_command(),
        stdin=read_fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        close_fds=True,
    )
    os.close(read_fd)

    def pump():
        try:
            if backlog:
                os.write(write_fd, backlog)
            while True:
                chunk = sock.recv(2048)
                if not chunk:
                    break
                os.write(write_fd, chunk)
        except OSError as error:
            log("канал закрыт: %s" % error)
        finally:
            try:
                os.close(write_fd)
            except OSError:
                pass

    def follow():
        stream = proc.stdout
        if stream is None:
            return
        for raw in stream:
            line = raw.decode("utf-8", "replace").rstrip()
            log("pppd: %s" % line)
            if "IP address" in line:
                log("Канал поднят. На навигаторе откройте http://%s:4731/" % LOCAL_IP)
        code = proc.wait()
        log("pppd завершился с кодом %s" % code)

    threading.Thread(target=pump, name="ppp-pump", daemon=True).start()
    threading.Thread(target=follow, name="ppp-log", daemon=True).start()
    return proc
