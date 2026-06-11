/******************** CUE HARDWARE FIRMWARE (THIN I/O LAYER) ******************
  This sketch contains NO experiment logic. It is a dumb hardware server:

    * Detects IR beam breaks and reports their edges over Serial.
    * Accepts text commands to actuate the reward pumps, the gate servo,
      the IR emitters, and (stubbed) a tone/buzzer.

  All trial logic — reward probabilities, stimulus assignment, choice timing,
  CSV logging — lives in the Python controller, which talks to this board
  through the Motor / Reward / IR / Tone classes (over one SerialLink).

  Wiring (unchanged from the original cue.ino):
    INNER RIGHT:  LED emitter pin 6   | Receiver pin 19
    CENTER:       LED emitter pin 8   | Receiver pin 18
    INNER LEFT:   LED emitter pin 10  | Receiver pin 2
    LEFT  reward pump  pin 40
    RIGHT reward pump  pin 44
    Gate servo         pin 48   (60 deg = OPEN, 180 deg = CLOSE)
    Buzzer/tone        pin 9    (NOT WIRED YET — TONE command is stubbed)

  ---------------------------------------------------------------------------
  PROTOCOL
  ---------------------------------------------------------------------------
  Commands IN — each framed as  $<COMMAND><newline>  (the leading '$' marks the
  start of a command; newline ends it). Case-insensitive. Examples:
    $PING           -> replies "PONG"
    $REWARD L       -> pulse LEFT pump for REWARD_MS
    $REWARD R       -> pulse RIGHT pump for REWARD_MS
    $SERVO <angle>  -> turn the gate servo to <angle> deg (0..180)
    $EMIT ON        -> IR emitters ON
    $EMIT OFF       -> IR emitters OFF
    $TONE <hz> <ms> -> STUBBED (logs only; no buzzer wired yet)
    $?              -> reprint the banner
  Bytes received outside a $...command are ignored.

  Events / replies OUT:
    READY                              (once, at boot)
    IR <CHANNEL> BROKEN <millis>       on a clear->broken edge
    IR <CHANNEL> CLEAR  <millis>       on a broken->clear edge
        CHANNEL is one of: INNER_LEFT  CENTER  INNER_RIGHT
    plus human-readable ACK lines for each actuation command.

  Serial: 115200 baud.
******************************************************************************/

#include <Servo.h>

// IR LED emitter pins (OUTPUT)
#define LED_IR   6
#define LED_C    8
#define LED_IL   10

// Receiver pins (INPUT_PULLUP)
#define RX_IR    19
#define RX_C     18
#define RX_IL    2

// Reward pump pins (OUTPUT)
#define REWARD_L 40
#define REWARD_R 44

// Gate servo
#define SERVO_PIN 48
const int SERVO_OPEN_DEG  = 60;
const int SERVO_CLOSE_DEG = 180;
Servo gateServo;

// Buzzer / tone output (NOT WIRED YET — TONE is stubbed below).
#define BUZZER_PIN 9

/******************** SETTINGS ************************************************/
const bool BROKEN_IS_LOW = false;            // matches original cue.ino
const unsigned long DEBOUNCE_MS = 30;        // edge-report debounce
const unsigned long REWARD_MS   = 100;       // reward pump pulse width

/******************** IR CHANNEL TABLE ****************************************/
struct Channel {
  const char* name;
  int ledPin;
  int rxPin;
  bool lastBroken;
  unsigned long lastEdgeMs;
};

Channel channels[] = {
  { "INNER_LEFT",  LED_IL, RX_IL, false, 0 },
  { "CENTER",      LED_C,  RX_C,  false, 0 },
  { "INNER_RIGHT", LED_IR, RX_IR, false, 0 },
};
const int NUM_CHANNELS = sizeof(channels) / sizeof(channels[0]);

/******************** HELPERS *************************************************/
bool isBroken(int pin) {
  int v = digitalRead(pin);
  return BROKEN_IS_LOW ? (v == LOW) : (v == HIGH);
}

void setEmitters(bool on) {
  digitalWrite(LED_IR, on ? HIGH : LOW);
  digitalWrite(LED_C,  on ? HIGH : LOW);
  digitalWrite(LED_IL, on ? HIGH : LOW);
  Serial.print(millis()); Serial.print(F("  EMITTERS "));
  Serial.println(on ? F("ON") : F("OFF"));
}

void rewardLeft() {
  Serial.print(millis()); Serial.println(F("  REWARD LEFT ON"));
  digitalWrite(REWARD_L, HIGH);
  delay(REWARD_MS);
  digitalWrite(REWARD_L, LOW);
  Serial.print(millis()); Serial.println(F("  REWARD LEFT OFF"));
}

void rewardRight() {
  Serial.print(millis()); Serial.println(F("  REWARD RIGHT ON"));
  digitalWrite(REWARD_R, HIGH);
  delay(REWARD_MS);
  digitalWrite(REWARD_R, LOW);
  Serial.print(millis()); Serial.println(F("  REWARD RIGHT OFF"));
}

// Turn the gate servo to an absolute angle (clamped to 0..180).
void servoTo(int deg) {
  if (deg < 0)   deg = 0;
  if (deg > 180) deg = 180;
  gateServo.write(deg);
  Serial.print(millis()); Serial.print(F("  SERVO -> "));
  Serial.print(deg); Serial.println(F(" deg"));
}

// STUB: real buzzer not wired yet. Logs the request so the Python side can be
// developed/tested now; swap in tone(BUZZER_PIN, hz, ms) when hardware lands.
void toneStub(long hz, long ms) {
  Serial.print(millis()); Serial.print(F("  TONE STUB hz="));
  Serial.print(hz); Serial.print(F(" ms="));
  Serial.print(ms); Serial.println(F("  (no buzzer wired)"));
  // pinMode(BUZZER_PIN, OUTPUT); tone(BUZZER_PIN, hz, ms);   // <- enable later
}

/******************** COMMAND PARSER ******************************************/
void printBanner() {
  Serial.println();
  Serial.println(F("################################################################"));
  Serial.println(F("  CUE HARDWARE FIRMWARE (thin I/O layer)"));
  Serial.println(F("################################################################"));
  Serial.print  (F("  BROKEN_IS_LOW = "));
  Serial.println(BROKEN_IS_LOW ? F("true") : F("false"));
  Serial.println(F("  Commands ($-prefixed): $PING | $REWARD L|R | $SERVO <angle>"));
  Serial.println(F("            | $EMIT ON|OFF | $TONE <hz> <ms> | $?"));
  Serial.println(F("  Emits:    IR <CHANNEL> BROKEN|CLEAR <millis>"));
  Serial.println();
}

void handleServo(const String& s) {
  // Expect: SERVO <angle>
  int sp = s.indexOf(' ');
  if (sp > 0) {
    servoTo(s.substring(sp + 1).toInt());
  } else {
    Serial.println(F("ERR SERVO needs an angle"));
  }
}

void handleTone(const String& s) {
  // Expect: TONE <hz> <ms>
  long hz = 1000, ms = 200;
  int sp1 = s.indexOf(' ');
  if (sp1 > 0) {
    int sp2 = s.indexOf(' ', sp1 + 1);
    if (sp2 > 0) {
      hz = s.substring(sp1 + 1, sp2).toInt();
      ms = s.substring(sp2 + 1).toInt();
    } else {
      hz = s.substring(sp1 + 1).toInt();
    }
  }
  toneStub(hz, ms);
}

void handleCommand(String s) {
  s.trim();
  if (s.length() == 0) return;

  if      (s.equalsIgnoreCase("PING"))       Serial.println(F("PONG"));
  else if (s.equalsIgnoreCase("REWARD L"))   rewardLeft();
  else if (s.equalsIgnoreCase("REWARD R"))   rewardRight();
  else if (s.equalsIgnoreCase("EMIT ON"))    setEmitters(true);
  else if (s.equalsIgnoreCase("EMIT OFF"))   setEmitters(false);
  else if (s.equalsIgnoreCase("?"))          printBanner();
  else if (s.length() >= 6 &&
           (s[0] == 'S' || s[0] == 's') &&
           (s[1] == 'E' || s[1] == 'e'))     handleServo(s);
  else if (s.length() >= 4 &&
           (s[0] == 'T' || s[0] == 't') &&
           (s[1] == 'O' || s[1] == 'o'))     handleTone(s);
  else {
    Serial.print(F("ERR unknown command: "));
    Serial.println(s);
  }
}

/******************** IR EDGE REPORTER ****************************************/
void pollIR() {
  unsigned long t = millis();
  for (int i = 0; i < NUM_CHANNELS; i++) {
    Channel& ch = channels[i];
    if (t - ch.lastEdgeMs < DEBOUNCE_MS) continue;

    bool now = isBroken(ch.rxPin);
    if (now && !ch.lastBroken) {
      Serial.print(F("IR ")); Serial.print(ch.name);
      Serial.print(F(" BROKEN ")); Serial.println(t);
      ch.lastEdgeMs = t;
      ch.lastBroken = now;
    } else if (!now && ch.lastBroken) {
      Serial.print(F("IR ")); Serial.print(ch.name);
      Serial.print(F(" CLEAR ")); Serial.println(t);
      ch.lastEdgeMs = t;
      ch.lastBroken = now;
    }
  }
}

/******************** SETUP / LOOP ********************************************/
String cmdBuf = "";
bool inCommand = false;          // true between a '$' and its terminator

void flushCommand() {
  if (cmdBuf.length() > 0) {
    handleCommand(cmdBuf);
    cmdBuf = "";
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(LED_IR, OUTPUT);
  pinMode(LED_C,  OUTPUT);
  pinMode(LED_IL, OUTPUT);

  pinMode(RX_IR, INPUT_PULLUP);
  pinMode(RX_C,  INPUT_PULLUP);
  pinMode(RX_IL, INPUT_PULLUP);

  pinMode(REWARD_L, OUTPUT); digitalWrite(REWARD_L, LOW);
  pinMode(REWARD_R, OUTPUT); digitalWrite(REWARD_R, LOW);

  gateServo.attach(SERVO_PIN);
  gateServo.write(SERVO_CLOSE_DEG);

  setEmitters(true);

  printBanner();
  Serial.println(F("READY"));
}

void loop() {
  // 1) report IR edges
  pollIR();

  // 2) drain inbound commands.
  //    Every command is framed as:  $<COMMAND><newline>
  //    '$' marks the start of a command (and flushes any previous one);
  //    newline (or the next '$') ends it. Bytes received outside a command
  //    (before a '$') are ignored, so boot noise / stray input can't trigger
  //    anything.
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '$') {
      flushCommand();          // end any in-progress command, start a new one
      inCommand = true;
    } else if (c == '\n' || c == '\r') {
      flushCommand();
      inCommand = false;
    } else if (inCommand) {
      cmdBuf += c;
      if (cmdBuf.length() > 48) { cmdBuf = ""; inCommand = false; }  // overflow guard
    }
    // else: byte outside a command -> ignore
  }

  delay(2);
}
