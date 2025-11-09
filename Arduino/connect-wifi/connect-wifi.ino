#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>  // DÙNG THƯ VIỆN NÀY: Frank de Brabander
#include <Wire.h>
#include <Preferences.h>

// --- Định nghĩa ---
const char* ssid = "Trinh";
const char* password = "28280303";

#define RST_PIN 22
#define SS_PIN 21
#define GREEN_LED_PIN 0
#define RED_LED_PIN 2
#define RELAY_PIN 5
#define TRIG_PIN 13
#define ECHO_PIN 27
#define MAX_UIDS 109

// --- Keypad ---
const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'}
};
byte rowPins[ROWS] = {17, 4, 14, 12};
byte colPins[COLS] = {25, 26, 32, 33};
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// --- LCD, RFID, Web ---
LiquidCrystal_I2C lcd(0x27, 20, 4);
WebServer server(80);
MFRC522 rfid(SS_PIN, RST_PIN);
Preferences preferences;

// --- Biến trạng thái ---
unsigned long doorOpenTime = 0;
const unsigned long doorOpenDuration = 5000;
bool doorIsOpen = false;
String currentPin = "";
String authorizedUIDs[MAX_UIDS];
int numAuthorizedUIDs = 0;
int currentCardIndex = 0;
bool isCardMode = false;
String inputPin = "";
bool changePinMode = false;
String newPin = "";
bool pinValidated = false;
float distance = 0;
unsigned long lastDistanceMeasureTime = 0;
const unsigned long idleMeasureInterval = 1000;
const unsigned long activeMeasureInterval = 500;
bool obstacleDetected = false;
const float obstacleThreshold = 100;

// --- PIN_REQUIRED ---
bool waitingForPin = false;
unsigned long pinEntryStartTime = 0;
const unsigned long pinEntryTimeout = 30000;

// --- Hàm nguyên mẫu ---
void loadDataFromFlash();
void savePinToFlash(String pinToSave);
void saveUIDsToFlash();
bool checkLCD();
void openDoor();
void closeDoor();
void addCard();
void deleteCard();
void displayCard();
void measureDistance();
void resetPinEntryMode();
void handleKeypad(char key);
void clearLine(int line);

// =================================================================
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Wire.begin(15, 16);
  if (!checkLCD()) {
    Serial.println("LCD not found!");
  }
  lcd.init();
  lcd.backlight();
  lcd.begin(20, 4);

  loadDataFromFlash();

  lcd.setCursor(0, 0); lcd.print("DOOR CLOSED    ");
  lcd.setCursor(0, 1); lcd.print("PIN: ");
  lcd.setCursor(0, 2); lcd.print("SYSTEM READY   ");
  lcd.setCursor(0, 3); lcd.print("IP: ");

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  closeDoor();

  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    String ip = WiFi.localIP().toString();
    Serial.println("\nWiFi connected: " + ip);
    lcd.setCursor(4, 3); lcd.print(ip);
  } else {
    Serial.println("\nWiFi failed");
    lcd.setCursor(0, 2); lcd.print("WIFI ERROR     ");
    while (true);
  }

  // Web routes
  server.on("/SUCCESS", HTTP_GET, []() {
    if (server.hasArg("key") && server.arg("key") == "28280303") {
      openDoor();
      server.send(200, "text/plain", "Door opened");
    } else {
      server.send(401, "text/plain", "Unauthorized");
    }
  });

  server.on("/FAIL", HTTP_GET, []() {
    digitalWrite(RED_LED_PIN, HIGH);
    clearLine(2); lcd.print("ACCESS DENIED  ");
    server.send(200, "text/plain", "Access denied");
    delay(2000);
    digitalWrite(RED_LED_PIN, LOW);
    clearLine(2);
  });

  server.on("/CLOSE", HTTP_GET, []() {
    closeDoor();
    server.send(200, "text/plain", "Door closed");
  });

  server.begin();
  SPI.begin();
  rfid.PCD_Init();
}

// =================================================================
void loop() {
  server.handleClient();

  // === Serial từ Python ===
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    Serial.println("[CMD] " + cmd);

    if (cmd == "PIN_REQUIRED") {
      waitingForPin = true;
      inputPin = "";
      pinEntryStartTime = millis();
      clearLine(2);
      lcd.setCursor(0, 2); lcd.print("ENTER PIN TO OPEN");
      lcd.setCursor(5, 1); lcd.print("    ");
      Serial.println("PIN_PROMPT");
    }
    else if (cmd == "SUCCESS") {
      openDoor();
      clearLine(2);
      lcd.print("DOOR OPENED    ");
    }
    else if (cmd == "FAIL") {
      digitalWrite(RED_LED_PIN, HIGH);
      clearLine(2); lcd.print("ACCESS DENIED  ");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
    }
    else if (cmd == "RECOGNIZING") {
      clearLine(2); lcd.print("RECOGNIZING... ");
    }
  }

  // === Timeout PIN ===
  if (waitingForPin && (millis() - pinEntryStartTime > pinEntryTimeout)) {
    waitingForPin = false;
    clearLine(2); lcd.print("PIN TIMEOUT    ");
    Serial.println("PIN_TIMEOUT");
    delay(2000);
    clearLine(2);
    inputPin = "";
    lcd.setCursor(5, 1); lcd.print("    ");
  }

  // === Đo khoảng cách ===
  unsigned long currentTime = millis();
  unsigned long interval = obstacleDetected ? activeMeasureInterval : idleMeasureInterval;
  if (currentTime - lastDistanceMeasureTime >= interval) {
    measureDistance();
    lastDistanceMeasureTime = currentTime;
  }

  // === RFID ===
  if (!isCardMode && !waitingForPin && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String cardUID = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      cardUID += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
      cardUID += String(rfid.uid.uidByte[i], HEX);
    }
    cardUID.toUpperCase();

    bool isAuthorized = false;
    for (int i = 0; i < numAuthorizedUIDs; i++) {
      if (authorizedUIDs[i] == cardUID) {
        isAuthorized = true;
        break;
      }
    }

    if (isAuthorized) {
      openDoor();
      clearLine(2); lcd.print("OPEN BY RFID   ");
    } else {
      digitalWrite(RED_LED_PIN, HIGH);
      clearLine(2); lcd.print("INVALID CARD   ");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
  }

  // === XỬ LÝ PHÍM ===
  char key = keypad.getKey();
  if (key) {
    handleKeypad(key);
  }

  // === ĐÓNG CỬA SAU 5S ===
  if (doorIsOpen && (millis() - doorOpenTime >= doorOpenDuration)) {
    closeDoor();
  }
}

// =================================================================
void resetPinEntryMode() {
  waitingForPin = false;
  clearLine(2);
  lcd.setCursor(5, 1); lcd.print("    ");
}

void loadDataFromFlash() {
  preferences.begin("smartlock", false);
  currentPin = preferences.getString("pin", "1234");
  numAuthorizedUIDs = preferences.getInt("uid_count", 0);
  for (int i = 0; i < numAuthorizedUIDs; i++) {
    String key = "uid_" + String(i);
    authorizedUIDs[i] = preferences.getString(key.c_str(), "");
  }
  if (numAuthorizedUIDs == 0) {
    authorizedUIDs[0] = "C35A0905";
    numAuthorizedUIDs = 1;
    preferences.putInt("uid_count", 1);
    preferences.putString("uid_0", "C35A0905");
  }
  preferences.end();
}

void savePinToFlash(String pinToSave) {
  preferences.begin("smartlock", false);
  preferences.putString("pin", pinToSave);
  preferences.end();
  currentPin = pinToSave;
}

void saveUIDsToFlash() {
  preferences.begin("smartlock", false);
  preferences.putInt("uid_count", numAuthorizedUIDs);
  for (int i = 0; i < numAuthorizedUIDs; i++) {
    preferences.putString(("uid_" + String(i)).c_str(), authorizedUIDs[i]);
  }
  for (int i = numAuthorizedUIDs; i < MAX_UIDS; i++) {
    String k = "uid_" + String(i);
    if (preferences.isKey(k.c_str())) preferences.remove(k.c_str());
  }
  preferences.end();
}

void addCard() {
  clearLine(2); lcd.print("SCAN NEW CARD  ");
  clearLine(3); lcd.print("               ");

  unsigned long startTime = millis();
  while (millis() - startTime < 5000) {
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
      String cardUID = "";
      for (byte i = 0; i < rfid.uid.size; i++) {
        cardUID += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
        cardUID += String(rfid.uid.uidByte[i], HEX);
      }
      cardUID.toUpperCase();

      for (int i = 0; i < numAuthorizedUIDs; i++) {
        if (authorizedUIDs[i] == cardUID) {
          clearLine(2); lcd.print("CARD EXISTS    ");
          delay(2000);
          rfid.PICC_HaltA(); rfid.PCD_StopCrypto1();
          return;
        }
      }

      if (numAuthorizedUIDs < MAX_UIDS) {
        authorizedUIDs[numAuthorizedUIDs++] = cardUID;
        saveUIDsToFlash();
        clearLine(2); lcd.print("CARD ADDED     ");
      } else {
        clearLine(2); lcd.print("CARD LIST FULL ");
      }
      delay(2000);
      rfid.PICC_HaltA(); rfid.PCD_StopCrypto1();
      return;
    }
  }
  clearLine(2); lcd.print("TIMEOUT        ");
  delay(2000);
}

void deleteCard() {
  if (numAuthorizedUIDs == 0) {
    clearLine(2); lcd.print("NO CARDS       ");
    delay(2000); return;
  }
  clearLine(2); lcd.print("DELETE CARD "); lcd.print(currentCardIndex + 1); lcd.print("?");
  clearLine(3); lcd.print("1: YES 2: NO   ");

  unsigned long startTime = millis();
  while (millis() - startTime < 5000) {
    char k = keypad.getKey();
    if (k == '1') {
      for (int i = currentCardIndex; i < numAuthorizedUIDs - 1; i++) {
        authorizedUIDs[i] = authorizedUIDs[i + 1];
      }
      numAuthorizedUIDs--;
      saveUIDsToFlash();
      if (currentCardIndex >= numAuthorizedUIDs && currentCardIndex > 0) currentCardIndex--;
      clearLine(2); lcd.print("CARD DELETED   ");
      delay(2000); return;
    } else if (k == '2') {
      clearLine(2); lcd.print("CANCELLED      ");
      delay(2000); return;
    }
  }
  clearLine(2); lcd.print("TIMEOUT        ");
  delay(2000);
}

void openDoor() {
  if (doorIsOpen) { doorOpenTime = millis(); return; }
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RELAY_PIN, HIGH);
  doorIsOpen = true;
  doorOpenTime = millis();
  lcd.setCursor(0, 0); lcd.print("DOOR OPEN      ");
}

void closeDoor() {
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);
  doorIsOpen = false;
  pinValidated = false;
  lcd.setCursor(0, 0); lcd.print("DOOR CLOSED    ");
}

bool checkLCD() {
  Wire.beginTransmission(0x27);
  return Wire.endTransmission() == 0;
}

void displayCard() {
  if (numAuthorizedUIDs == 0) {
    clearLine(2); lcd.print("NO CARDS       ");
    clearLine(3); lcd.print("               ");
    return;
  }
  clearLine(2); lcd.print("CARD "); lcd.print(currentCardIndex + 1); lcd.print("/"); lcd.print(numAuthorizedUIDs);
  clearLine(3); lcd.print(authorizedUIDs[currentCardIndex] + " ");
}

void measureDistance() {
  digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  distance = duration * 0.034 / 2;

  if (distance > 0 && distance < 400) {
    obstacleDetected = (distance < obstacleThreshold);
  } else {
    obstacleDetected = false;
  }

  if (!changePinMode && !pinValidated && !isCardMode && !waitingForPin) {
    clearLine(2);
    if (distance > 0 && distance < 400) {
      lcd.print("DIST: "); lcd.print(distance, 0); lcd.print(" cm ");
    } else {
      lcd.print("DIST: OUT RANGE");
    }
  }
}

void handleKeypad(char key) {
  // === TRƯỜNG HỢP 1: ĐANG CHỜ NHẬP PIN SAU NHẬN DIỆN (GỬI VỀ PYTHON) ===
  if (waitingForPin) {
    pinEntryStartTime = millis(); // Reset timeout mỗi khi bấm phím

    if (key >= '0' && key <= '9') {
      if (inputPin.length() < 4) {
        inputPin += key;
        lcd.setCursor(5, 1);
        lcd.print(inputPin);
        lcd.print("    "); // Xóa ký tự dư
        Serial.println("[DEBUG] PIN Input: " + inputPin);
      }
    }
    else if (key == '#') {
      // Xác nhận PIN và gửi về Python
      if (inputPin.length() == 0) {
        clearLine(2);
        lcd.print("NHAP PIN TRUOC!");
        delay(1000);
        clearLine(2);
        lcd.setCursor(0, 2); lcd.print("ENTER PIN TO OPEN");
        return;
      }

      // GỬI PIN VỀ PYTHON ĐỂ KIỂM TRA
      Serial.println("PIN_ENTERED:" + inputPin);
      clearLine(2);
      lcd.print("CHECKING PIN...");
      inputPin = "";
      lcd.setCursor(5, 1); lcd.print("    ");
      waitingForPin = false; // Kết thúc trạng thái nhập PIN
    }
    return; // QUAN TRỌNG: Thoát khỏi hàm
  }

  // === TRƯỜNG HỢP 2: ĐANG ĐỔI PIN ===
  if (changePinMode) {
    if (key >= '0' && key <= '9') {
      if (newPin.length() < 4) {
        newPin += key;
        lcd.setCursor(5, 1);
        lcd.print(newPin);
        lcd.print("    ");
      }
    }
    else if (key == '#') {
      if (newPin.length() == 4) {
        savePinToFlash(newPin);
        clearLine(2); lcd.print("PIN CHANGE OK  ");
        digitalWrite(GREEN_LED_PIN, HIGH); 
        delay(2000); 
        digitalWrite(GREEN_LED_PIN, LOW);
      } else {
        clearLine(2); lcd.print("PIN MUST BE 4  ");
        digitalWrite(RED_LED_PIN, HIGH); 
        delay(2000); 
        digitalWrite(RED_LED_PIN, LOW);
      }
      changePinMode = false; 
      newPin = ""; 
      inputPin = ""; 
      pinValidated = false;
      resetPinEntryMode();
    }
    return; // Thoát khỏi hàm
  }

  // === TRƯỜNG HỢP 3: NHẬP PIN BÌNH THƯỜNG (MỞ CỬA TRỰC TIẾP) ===
  if (key >= '0' && key <= '9') {
    if (inputPin.length() < 4) {
      inputPin += key;
      lcd.setCursor(5, 1);
      lcd.print(inputPin);
      lcd.print("    ");
    }
  }
  else if (key == '#') {
    if (inputPin == currentPin) {
      pinValidated = true;
      openDoor();
      clearLine(2); lcd.print("OPEN BY PIN    ");
    } else {
      clearLine(2); lcd.print("WRONG PIN      ");
      digitalWrite(RED_LED_PIN, HIGH); 
      delay(2000); 
      digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
    }
    inputPin = ""; 
    lcd.setCursor(5, 1); lcd.print("    ");
  }
  else if (key == '*') {
    if (pinValidated) {
      changePinMode = true; 
      newPin = ""; 
      inputPin = "";
      clearLine(2); lcd.print("ENTER NEW PIN  ");
      lcd.setCursor(5, 1); lcd.print("    ");
    } else {
      clearLine(2); lcd.print("DENIED         ");
      digitalWrite(RED_LED_PIN, HIGH); 
      delay(2000); 
      digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
    }
  }
  // === TRƯỜNG HỢP 4: QUẢN LÝ THẺ ===
  else if (pinValidated) {
    if (key == 'A') { 
      isCardMode = true; 
      currentCardIndex = 0; 
      displayCard(); 
    }
    else if (key == 'B') { 
      isCardMode = true; 
      addCard(); 
      displayCard(); 
    }
    else if (key == 'C') { 
      isCardMode = true; 
      deleteCard(); 
      displayCard(); 
    }
    else if (key == 'D' && isCardMode) {
      isCardMode = false;
      lcd.clear();
      lcd.setCursor(0, 0); lcd.print(doorIsOpen ? "DOOR OPEN      " : "DOOR CLOSED    ");
      lcd.setCursor(0, 1); lcd.print("PIN: ");
      lcd.setCursor(0, 3); lcd.print("IP: "); lcd.print(WiFi.localIP().toString());
    }
  }
}

void clearLine(int line) {
  lcd.setCursor(0, line);
  lcd.print("                    ");
  lcd.setCursor(0, line);
}