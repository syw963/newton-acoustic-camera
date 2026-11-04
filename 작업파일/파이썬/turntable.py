"""회전판(아두이노) 제어 모듈.

아두이노에 올린 turntable.ino는 시리얼로 한 줄짜리 명령을 받는다.
이 모듈은 그 명령을 파이썬 함수로 감싼다. 시리얼 모니터에 직접 치던 것을
코드로 보내는 것과 같다.

    from turntable import Turntable
    with Turntable() as t:        # 포트 자동 찾기. 아두이노 없이 연습하려면 Turntable("sim")
        t.home()                  # 원점 찾기
        t.goto(-30)               # 절대 각도로 이동
        print(t.status())

명령이 끝나면 아두이노는 "ok"를, 실패하면 "err ..."을 보낸다.
command()는 "ok"가 올 때까지 기다리고, "err"가 오면 TurntableError를 낸다.
"""

import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # pyserial이 없어도 시뮬레이터는 쓸 수 있게 함
    serial = None
    list_ports = None

BAUD = 115200

# USB 제조사 번호(VID)로 아두이노를 알아본다. 11번가 호환 보드는 대부분 CH340이다.
KNOWN_VIDS = {
    0x2341: "Arduino 정품",
    0x2A03: "Arduino 정품",
    0x1A86: "CH340 (호환 보드)",
    0x0403: "FTDI (호환 보드)",
    0x10C4: "CP210x (호환 보드)",
}


class TurntableError(Exception):
    """아두이노가 'err ...'로 답했거나 응답이 없을 때."""


def find_arduino_ports():
    """아두이노로 보이는 시리얼 포트 목록 [(포트 이름, 설명)]."""
    if list_ports is None:
        return []
    found = []
    for p in list_ports.comports():
        if p.vid in KNOWN_VIDS:
            found.append((p.device, KNOWN_VIDS[p.vid]))
        elif any(k in (p.device or "") for k in ("usbmodem", "usbserial", "wchusbserial")):
            found.append((p.device, p.description or "USB 시리얼"))
    return found


class Turntable:
    def __init__(self, port=None, verbose=True):
        """port: 'COM3', '/dev/cu.usbmodem1101' 같은 포트 이름. 비우면 자동으로 찾는다.
        'sim'이면 아두이노 없이 시뮬레이터에 연결한다."""
        self.verbose = verbose
        if port == "sim":
            self.ser = FakeArduino()
            self.port = "sim"
        else:
            if serial is None:
                raise TurntableError("pyserial이 없어요. pip install -r requirements.txt 를 먼저 하세요.")
            if port is None:
                ports = find_arduino_ports()
                if not ports:
                    raise TurntableError(
                        "아두이노를 찾지 못했어요. USB 선을 확인하고, 아두이노 IDE의 시리얼 모니터를 닫으세요. "
                        "포트를 직접 주려면 --port COM3 처럼 쓰세요. 아두이노 없이 연습하려면 --port sim")
                port = ports[0][0]
            self.port = port
            try:
                self.ser = serial.Serial(port, BAUD, timeout=0.1)
            except serial.SerialException as e:
                raise TurntableError(f"{port}를 열 수 없어요. 아두이노 IDE 시리얼 모니터가 열려 있으면 닫으세요. ({e})")
        self._wait_ready()

    # ---------- 저수준 ----------
    def _log(self, s):
        if self.verbose:
            print(s)

    def _readline(self):
        raw = self.ser.readline()
        if not raw:
            return None
        return raw.decode("utf-8", errors="replace").strip()

    def _wait_ready(self, timeout=4.0):
        # 포트를 열면 아두이노 UNO가 다시 켜진다(리셋). 'turntable ready'가 올 때까지 기다린다.
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self._readline()
            if line and "ready" in line:
                self._log(f"[연결] {self.port}: {line}")
                return
        self._log(f"[연결] {self.port}: 준비 메시지가 없어 그대로 진행해요")

    def command(self, cmd, timeout=30.0):
        """명령 한 줄을 보내고 'ok'까지 받은 줄들을 돌려준다."""
        self._log(f">> {cmd}")
        self.ser.write((cmd + "\n").encode("ascii"))
        lines = []
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self._readline()
            if line is None or line == "":
                continue
            if line == "ok":
                return lines
            if line.startswith("err"):
                self._log(f"<< {line}")
                raise TurntableError(line[3:].strip())
            self._log(f"<< {line}")
            lines.append(line)
        raise TurntableError(f"'{cmd}'에 {timeout:.0f}초 동안 응답이 없어요")

    # ---------- 명령 ----------
    def status(self):
        """{'angle_deg': -30.0, 'steps': -267, 'limit': '떨어짐', 'driver': '켜짐', 'homed': 'yes'}"""
        lines = self.command("?")
        out = {}
        for part in (lines[-1] if lines else "").split():
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    v = float(v) if k == "angle_deg" else int(v) if k == "steps" else v
                except ValueError:
                    pass
                out[k] = v
        return out

    def enable(self, on=True):
        """모터 드라이버 켜기/끄기. 끄면 모터에 힘이 빠지고 잡음이 줄 수 있다."""
        self.command("e1" if on else "e0")

    def home(self):
        """리밋 스위치로 원점을 찾고 0°로 간다."""
        self.command("h", timeout=40)

    def bench_origin(self):
        """벤치 원점: 리밋 스위치 없이 지금 위치를 0°로 믿는다. 조립 전 책상 위 시험용.
        (turntable.ino 11/4 판 이후에 있는 o 명령)"""
        self.command("o")

    def goto(self, deg):
        """원점 기준 절대 각도로 이동 (-65 ~ +65)."""
        self.command(f"g{deg:.3f}")

    def nudge(self, deg):
        """원점 없이 조금 움직이기 (배선 시험용, ±30° 이내)."""
        self.command(f"m{deg:.3f}")

    def set_zero(self):
        """지금 위치를 0°로 정한다. LIMIT_ANGLE_DEG를 고칠 값을 알려 준다."""
        return self.command("z")

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeArduino:
    """turntable.ino의 응답을 흉내 내는 가짜 아두이노. 하드웨어 없이 코드를 연습할 때 쓴다.
    이동 시간도 실제처럼 걸린다(약 90°/s)."""

    STEPS_PER_REV = 3200
    LIMIT_ANGLE_DEG = -70.0

    def __init__(self):
        self.pos = 0  # 스텝. 원점을 찾기 전에는 임의 위치
        self.homed = False
        self.enabled = False
        self.queue = [(time.time() + 0.3, "turntable ready. ? 로 상태 확인")]

    def _deg(self, s):
        return s * 360.0 / self.STEPS_PER_REV

    def _steps(self, d):
        return round(d * self.STEPS_PER_REV / 360.0)

    def _say(self, delay, *lines):
        t = max(time.time(), self.queue[-1][0] if self.queue else 0.0) + delay
        for ln in lines:
            self.queue.append((t, ln))

    def write(self, data):
        for cmd in data.decode("ascii").strip().splitlines():
            self._handle(cmd.strip().replace(" ", ""))

    def _handle(self, s):
        if not s:
            return
        c, arg = s[0], s[1:]
        try:
            v = float(arg) if arg else 0.0
        except ValueError:
            v = 0.0
        if c == "?":
            lim = "눌림" if self._deg(self.pos) <= self.LIMIT_ANGLE_DEG else "떨어짐"
            self._say(0.01, f"angle_deg={self._deg(self.pos):.3f} steps={self.pos} limit={lim} "
                            f"driver={'켜짐' if self.enabled else '꺼짐'} homed={'yes' if self.homed else 'no'}", "ok")
        elif c == "e":
            self.enabled = v > 0.5
            self._say(0.01, "ok")
        elif c == "w":
            self._say(0.01, "10초 동안 스위치를 눌러 보세요")
            self._say(0.5, "눌림")  # 시뮬레이터는 한 번 누른 것으로 함
            self._say(0.3, "떨어짐")
            self._say(0.5, "ok")
        elif c == "m":
            if abs(v) > 30:
                self._say(0.01, "err m은 ±30° 이내")
                return
            self.enabled = True
            self.pos += self._steps(v)
            self._say(abs(v) / 90 + 0.1, "ok")
        elif c == "h":
            self.enabled = True
            self.pos = 0
            self.homed = True
            self._say(2.5, "ok")
        elif c == "o":
            self.pos = 0
            self.homed = True
            self._say(0.01, "벤치 원점: 지금 위치를 0°로 정함 (리밋 스위치 확인 안 함)", "ok")
        elif c == "g":
            if not self.homed:
                self._say(0.01, "err 먼저 h로 원점을 찾으세요")
                return
            if v < -65 or v > 65:
                self._say(0.01, "err 범위 밖")
                return
            self.enabled = True
            dist = abs(v - self._deg(self.pos))
            self.pos = self._steps(v)
            self._say(dist / 90 + 0.1, "ok")
        elif c == "z":
            if not self.homed:
                self._say(0.01, "err 먼저 h로 원점을 찾으세요")
                return
            self._say(0.01, f"LIMIT_ANGLE_DEG를 {self.LIMIT_ANGLE_DEG - self._deg(self.pos):.2f} 로 고쳐 다시 업로드하세요", "ok")
            self.pos = 0
        else:
            self._say(0.01, "err 모르는 명령")

    def readline(self):
        if self.queue and self.queue[0][0] <= time.time():
            return (self.queue.pop(0)[1] + "\r\n").encode("utf-8")
        time.sleep(0.02)
        return b""

    def close(self):
        pass
