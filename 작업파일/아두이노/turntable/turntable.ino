// 뉴턴 음향카메라 회전판 제어 (배선 테스트 겸용)
// 보드: 아두이노 UNO + CNC 쉴드 V3, 모터는 X축 자리(A4988), 리밋 스위치는 X- 단자
// 시리얼 모니터: 115200, 줄 끝 "새 줄(NL)"
//
// 명령 (한 줄에 하나, 끝나면 "ok" 또는 "err ..."를 출력)
//   ?        상태 보기 (각도, 리밋 스위치, 드라이버 켜짐, 원점 여부)
//   w        리밋 스위치 확인 모드 10초 (누를 때마다 출력)
//   e1 / e0  모터 드라이버 켜기 / 끄기
//   m<각도>  원점 없이 상대 이동 (배선 테스트용, ±30° 이내) 예: m10
//   h        원점 찾기 (리밋 스위치까지 갔다가 0°로 이동)
//   g<각도>  절대 각도로 이동 (원점을 찾은 뒤에만) 예: g-45
//   z        지금 위치를 0°로 정함 (카메라 십자선에 맞춘 뒤) → LIMIT_ANGLE_DEG 값을 알려 줌

#include <Arduino.h>

// ---- 핀 (CNC 쉴드 V3, X축) ----
const uint8_t PIN_STEP  = 2;
const uint8_t PIN_DIR   = 5;
const uint8_t PIN_EN    = 8;   // LOW = 드라이버 켜짐
const uint8_t PIN_LIMIT = 9;   // X- 와 X+ 단자가 모두 이 핀

// ---- 설정 (실물에 맞춰 고침) ----
const long  STEPS_PER_REV    = 3200;   // 200스텝 × 1/16 마이크로스텝
const bool  DIR_INVERT       = false;  // m10 했을 때 반대로 돌면 true
const float LIMIT_ANGLE_DEG  = -70.0;  // 리밋 스위치가 눌리는 각도. z 명령이 알려 주는 값으로 고침
const float SOFT_MIN_DEG     = -65.0;  // g 명령 허용 범위
const float SOFT_MAX_DEG     = 65.0;
const unsigned int PERIOD_FAST = 1250; // 스텝 간격(µs). 1250 → 약 90°/s
const unsigned int PERIOD_START = 4000;// 가감속 시작 간격
const unsigned int PERIOD_HOME = 3000; // 원점 찾기 1차 속도
const unsigned int PERIOD_HOME_SLOW = 8000; // 원점 찾기 2차(정밀) 속도
const long RAMP_STEPS = 150;           // 가감속 구간 스텝 수

long pos = 0;          // 현재 위치 (스텝, 0° 기준)
bool homed = false;
bool enabled = false;

long degToSteps(float d) { return lround(d * STEPS_PER_REV / 360.0); }
float stepsToDeg(long s) { return s * 360.0 / STEPS_PER_REV; }

// COM-GND, NO-신호 배선 + 내부 풀업: 눌리면 LOW
bool limitRaw() { return digitalRead(PIN_LIMIT) == LOW; }
bool limitPressed() {
  for (uint8_t i = 0; i < 3; i++) {
    if (!limitRaw()) return false;
    delayMicroseconds(100);
  }
  return true;
}

void setEnable(bool on) {
  digitalWrite(PIN_EN, on ? LOW : HIGH);
  enabled = on;
  if (on) delay(5);
}

void stepOnce(int dir, unsigned int periodUs) {
  bool high = (dir > 0) != DIR_INVERT;
  digitalWrite(PIN_DIR, high ? HIGH : LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_STEP, HIGH);
  delayMicroseconds(3);
  digitalWrite(PIN_STEP, LOW);
  delayMicroseconds(periodUs - 5);
  pos += dir;
}

// n스텝 이동 (부호가 방향). 이동 중 리밋 스위치가 눌리면 멈추고 false
bool moveSteps(long n) {
  if (n == 0) return true;
  if (!enabled) setEnable(true);
  int dir = (n > 0) ? 1 : -1;
  long total = labs(n);
  for (long i = 0; i < total; i++) {
    long edge = min(i, total - 1 - i);
    unsigned int period = PERIOD_FAST;
    if (edge < RAMP_STEPS) {
      period = PERIOD_START - (long)(PERIOD_START - PERIOD_FAST) * edge / RAMP_STEPS;
    }
    if (homed && limitRaw() && limitPressed()) {
      homed = false;  // 위치를 믿을 수 없으므로 원점을 다시 찾아야 함
      Serial.println(F("err 이동 중 리밋 스위치가 눌려 멈춤. h로 원점을 다시 찾으세요"));
      return false;
    }
    stepOnce(dir, period);
  }
  return true;
}

bool home() {
  setEnable(true);
  homed = false;
  // 이미 눌려 있으면 + 방향으로 빠져나옴 (최대 30°)
  long guard = 0;
  while (limitPressed() && guard < degToSteps(30)) { stepOnce(+1, PERIOD_HOME); guard++; }
  if (limitPressed()) { Serial.println(F("err 스위치가 계속 눌려 있음 (배선 확인)")); return false; }
  for (long i = 0; i < degToSteps(3); i++) stepOnce(+1, PERIOD_HOME);

  // 1차: - 방향으로 최대 200° 안에서 스위치 찾기
  guard = 0;
  while (!limitPressed() && guard < degToSteps(200)) { stepOnce(-1, PERIOD_HOME); guard++; }
  if (!limitPressed()) { Serial.println(F("err 200° 안에서 리밋 스위치를 못 찾음 (배선·위치·DIR_INVERT 확인)")); return false; }

  // 2차: 3° 물러났다가 천천히 다시 눌러 정확한 위치 잡기
  for (long i = 0; i < degToSteps(3); i++) stepOnce(+1, PERIOD_HOME);
  guard = 0;
  while (!limitPressed() && guard < degToSteps(6)) { stepOnce(-1, PERIOD_HOME_SLOW); guard++; }
  if (!limitPressed()) { Serial.println(F("err 2차 접근에서 스위치를 못 찾음")); return false; }

  pos = degToSteps(LIMIT_ANGLE_DEG);
  // 스위치에서 3° 떨어진 뒤 0°로 이동 (스위치를 누른 채 움직이면 멈추므로 먼저 벗어남)
  for (long i = 0; i < degToSteps(3); i++) stepOnce(+1, PERIOD_HOME);
  homed = true;
  return moveSteps(-pos);
}

void printStatus() {
  Serial.print(F("angle_deg=")); Serial.print(stepsToDeg(pos), 3);
  Serial.print(F(" steps=")); Serial.print(pos);
  Serial.print(F(" limit=")); Serial.print(limitRaw() ? F("눌림") : F("떨어짐"));
  Serial.print(F(" driver=")); Serial.print(enabled ? F("켜짐") : F("꺼짐"));
  Serial.print(F(" homed=")); Serial.println(homed ? F("yes") : F("no"));
}

char buf[24];
uint8_t len = 0;

void handle(char *s) {
  char c = s[0];
  float v = atof(s + 1);
  bool ok = true;
  switch (c) {
    case '?': printStatus(); break;
    case 'e': setEnable(v > 0.5); break;
    case 'w': {
      Serial.println(F("10초 동안 스위치를 눌러 보세요"));
      bool last = limitRaw();
      unsigned long t0 = millis();
      while (millis() - t0 < 10000UL) {
        bool now = limitRaw();
        if (now != last) { Serial.println(now ? F("눌림") : F("떨어짐")); last = now; delay(20); }
      }
      break;
    }
    case 'm':
      if (fabs(v) > 30.0) { Serial.println(F("err m은 ±30° 이내")); ok = false; break; }
      ok = moveSteps(degToSteps(v));
      break;
    case 'h': ok = home(); break;
    case 'g':
      if (!homed) { Serial.println(F("err 먼저 h로 원점을 찾으세요")); ok = false; break; }
      if (v < SOFT_MIN_DEG || v > SOFT_MAX_DEG) { Serial.println(F("err 범위 밖")); ok = false; break; }
      ok = moveSteps(degToSteps(v) - pos);  // 매번 절대 스텝으로 계산해 오차가 쌓이지 않음
      break;
    case 'z':
      if (!homed) { Serial.println(F("err 먼저 h로 원점을 찾으세요")); ok = false; break; }
      Serial.print(F("LIMIT_ANGLE_DEG를 "));
      Serial.print(LIMIT_ANGLE_DEG - stepsToDeg(pos), 2);
      Serial.println(F(" 로 고쳐 다시 업로드하세요"));
      pos = 0;
      break;
    default: Serial.println(F("err 모르는 명령")); ok = false;
  }
  if (ok) Serial.println(F("ok"));
}

void setup() {
  pinMode(PIN_STEP, OUTPUT);
  pinMode(PIN_DIR, OUTPUT);
  pinMode(PIN_EN, OUTPUT);
  pinMode(PIN_LIMIT, INPUT_PULLUP);
  setEnable(false);  // 켜자마자 모터가 힘을 받지 않게
  Serial.begin(115200);
  Serial.println(F("turntable ready. ? 로 상태 확인"));
}

void loop() {
  while (Serial.available()) {
    char ch = Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      buf[len] = 0;
      if (len > 0) handle(buf);
      len = 0;
    } else if (len < sizeof(buf) - 1 && ch != ' ') {
      buf[len++] = ch;
    }
  }
}
