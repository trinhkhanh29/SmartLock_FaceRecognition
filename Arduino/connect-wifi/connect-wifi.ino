#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>
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
#define TEMP_CODE_LENGTH 6

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

// --- Biến trạng thái mã tạm ---
bool isTempCodeMode = false;
String tempCodeInput = "";
String YOUR_LOCK_ID = "";

// THÊM: Thông tin Backend API
const char* BACKEND_URL = "http://10.55.26.46:3000"; // <-- THAY IP NÀY BẰNG IP MÁY TÍNH CỦA BẠN

// =================================================================
// HÀM HỖ TRỢ - DI CHUYỂN LÊN ĐẦU (TRƯỚC setup)
void clearLine(int line) {
  lcd.setCursor(0, line);
  lcd.print("                    "); // 20 spaces
  lcd.setCursor(0, line);
}

void clearInputLine() {
  lcd.setCursor(5, 1);
  lcd.print("                "); // 16 spaces
  lcd.setCursor(5, 1);
}

void displayLockID() {
  clearLine(2);
  lcd.print("ID:");
  lcd.print(YOUR_LOCK_ID.substring(0, 12));
}

void displayIP() {
  clearLine(3);
  lcd.print("IP: ");
  lcd.print(WiFi.localIP().toString());
}

void restoreDefaultDisplay() {
  isCardMode = false;
  isTempCodeMode = false;
  changePinMode = false;
  waitingForPin = false;

  lcd.setCursor(0, 0); lcd.print(doorIsOpen ? "DOOR OPEN      " : "DOOR CLOSED    ");
  lcd.setCursor(0, 1); lcd.print("PIN: ");
  clearInputLine();
  displayLockID();
  displayIP();
  measureDistance();  // Cập nhật DIST nếu không có chế độ nào
}

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
    displayIP();  // ← DÙNG HÀM MỚI
  } else {
    Serial.println("\nWiFi failed");
    lcd.setCursor(0, 2); lcd.print("WIFI ERROR     ");
    while (true);
  }

  // === LẤY HOẶC SET LOCK ID ===
  preferences.begin("smartlock", false);
  YOUR_LOCK_ID = preferences.getString("lock_id", "");
  if (YOUR_LOCK_ID.length() == 0) {
    YOUR_LOCK_ID = "a03ab4496ccca125";
    preferences.putString("lock_id", YOUR_LOCK_ID);
    Serial.println("[SETUP] [INIT] Lock ID: " + YOUR_LOCK_ID);
  } else {
    Serial.println("[SETUP] [OK] Lock ID: " + YOUR_LOCK_ID);
  }
  preferences.end();

  // Hiển thị ID 3 giây
  displayLockID();
  delay(3000);
  clearLine(2); lcd.print("SYSTEM READY   ");

  Serial.println("[SETUP] Lock ID: " + YOUR_LOCK_ID);

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
      clearLine(2); lcd.print("ENTER PIN TO OPEN");
      clearInputLine();
      Serial.println("PIN_PROMPT");
    }
    else if (cmd == "SUCCESS") {
      openDoor();
      clearLine(2); lcd.print("DOOR OPENED    ");
      resetPinEntryMode();
    }
    else if (cmd == "FAIL") {
      digitalWrite(RED_LED_PIN, HIGH);
      clearLine(2); lcd.print("ACCESS DENIED  ");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
      resetPinEntryMode();
    }
    else if (cmd == "RECOGNIZING") {
      static String last = "";
      if (last != "RECOGNIZING... ") {
        clearLine(2); lcd.print("RECOGNIZING... ");
        last = "RECOGNIZING... ";
      }
    }
    else if (cmd == "RECOGNITION_DONE" || cmd == "SYSTEM_READY") {
      clearLine(2);
    }
  }

  // === Timeout PIN ===
  if (waitingForPin && (millis() - pinEntryStartTime > pinEntryTimeout)) {
    waitingForPin = false;
    clearLine(2); lcd.print("PIN TIMEOUT    ");
    Serial.println("PIN_TIMEOUT");
    delay(2000);
    clearLine(2);
    clearInputLine();
  }

  // === Đo khoảng cách ===
  unsigned long currentTime = millis();
  unsigned long interval = obstacleDetected ? activeMeasureInterval : idleMeasureInterval;
  if (currentTime - lastDistanceMeasureTime >= interval) {
    measureDistance();
    lastDistanceMeasureTime = currentTime;
  }

  // === RFID ===
  if (!isCardMode && !waitingForPin && !isTempCodeMode && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
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
  clearInputLine();
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
  restoreDefaultDisplay();  // ← SẠCH HOÀN TOÀN
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

  if (distance > 0 && distance < 400) {
    Serial.print("DISTANCE:");
    Serial.println(distance, 1);
  } else {
    Serial.println("DISTANCE:OUT_RANGE");
  }

  // Chỉ hiển thị khi KHÔNG có chế độ nào bật
  if (!changePinMode && !pinValidated && !isCardMode && !waitingForPin && !isTempCodeMode) {
    clearLine(2);
    if (distance > 0 && distance < 400) {
      lcd.print("DIST: "); lcd.print(distance, 0); lcd.print(" cm ");
    } else {
      lcd.print("DIST: OUT RANGE");
    }
  }
}

void handleKeypad(char key) {
  // === 1. NHẬP PIN SAU NHẬN DIỆN ===
  if (waitingForPin) {
    pinEntryStartTime = millis();
    if (key >= '0' && key <= '9' && inputPin.length() < 4) {
      inputPin += key;
      clearInputLine();
      lcd.print(inputPin);
      Serial.println("[DEBUG] PIN Input: " + inputPin);
    }
    else if (key == '#') {
      if (inputPin.length() == 0) {
        clearLine(2); lcd.print("NHAP PIN TRUOC!");
        delay(1000);
        clearLine(2); lcd.print("ENTER PIN TO OPEN");
        return;
      }
      Serial.println("PIN_ENTERED:" + inputPin);
      clearLine(2); lcd.print("CHECKING PIN...");
      clearInputLine();
      waitingForPin = false;
    }
    return;
  }

  // === 2. ĐỔI PIN ===
  if (changePinMode) {
    if (key >= '0' && key <= '9' && newPin.length() < 4) {
      newPin += key;
      clearInputLine();
      lcd.print(newPin);
    }
    else if (key == '#') {
      if (newPin.length() == 4) {
        savePinToFlash(newPin);
        clearLine(2); lcd.print("PIN CHANGE OK  ");
        digitalWrite(GREEN_LED_PIN, HIGH); delay(2000); digitalWrite(GREEN_LED_PIN, LOW);
      } else {
        clearLine(2); lcd.print("PIN MUST BE 4  ");
        digitalWrite(RED_LED_PIN, HIGH); delay(2000); digitalWrite(RED_LED_PIN, LOW);
      }
      changePinMode = false; newPin = ""; resetPinEntryMode();
    }
    return;
  }

  // === 3. NHẬP MÃ TẠM 6 SỐ ===
  if (isTempCodeMode) {
    if (key >= '0' && key <= '9' && tempCodeInput.length() < TEMP_CODE_LENGTH) {
      tempCodeInput += key;
      clearInputLine();
      lcd.print(tempCodeInput);
      int remaining = TEMP_CODE_LENGTH - tempCodeInput.length();
      if (remaining > 0) {
        lcd.print(" ("); lcd.print(remaining); lcd.print(")");
      }
    }
    else if (key == '#') {
      if (tempCodeInput.length() == TEMP_CODE_LENGTH) {
        clearLine(2); lcd.print("CHECKING CODE...");
        Serial.println("[TEMP_CODE] Verifying: " + tempCodeInput);
        
        if (verifyTempCodeWithServer(tempCodeInput)) {
          openDoor();
          clearLine(2); lcd.print("CODE ACCEPTED  ");
          digitalWrite(GREEN_LED_PIN, HIGH); delay(1000); digitalWrite(GREEN_LED_PIN, LOW);
          clearLine(3);
          displayLockID();
        } else {
          digitalWrite(RED_LED_PIN, HIGH);
          clearLine(2); lcd.print("INVALID CODE   ");
          delay(2000); digitalWrite(RED_LED_PIN, LOW);
          clearLine(2);
          clearLine(3);
        }
      } else {
        clearLine(2); lcd.print("CODE MUST BE 6 ");
        delay(1000);
        clearLine(2); lcd.print("Enter 6 digits:");
      }
      
      isTempCodeMode = false;
      tempCodeInput = "";
      clearInputLine();
    }
    else if (key == '*') {
      isTempCodeMode = false;
      tempCodeInput = "";
      clearLine(2); lcd.print("CANCELLED      ");
      clearLine(3);
      clearInputLine();
      Serial.println("[TEMP_CODE] Cancelled");
    }
    return;
  }

  // === 4. NHẬP PIN BÌNH THƯỜNG ===
  if (key >= '0' && key <= '9' && inputPin.length() < 4) {
    inputPin += key;
    clearInputLine();
    lcd.print(inputPin);
  }
  else if (key == '#') {
    if (inputPin == currentPin) {
      pinValidated = true;
      openDoor();
      clearLine(2); lcd.print("OPEN BY PIN    ");
    } else {
      clearLine(2); lcd.print("WRONG PIN      ");
      digitalWrite(RED_LED_PIN, HIGH); delay(2000); digitalWrite(RED_LED_PIN, LOW);
      clearLine(2);
    }
    inputPin = ""; clearInputLine();
  }
  else if (key == '*' && pinValidated) {
    changePinMode = true; newPin = ""; inputPin = "";
    clearLine(2); lcd.print("ENTER NEW PIN  ");
    clearInputLine();
  }
  else if (key == '*' && !pinValidated) {
    clearLine(2); lcd.print("DENIED         ");
    digitalWrite(RED_LED_PIN, HIGH); delay(2000); digitalWrite(RED_LED_PIN, LOW);
    clearLine(2);
  }

  // === 5. QUẢN LÝ THẺ ===
  else if (pinValidated) {
    if (key == 'A') { isCardMode = true; currentCardIndex = 0; displayCard(); }
    else if (key == 'B') { isCardMode = true; addCard(); displayCard(); }
    else if (key == 'C') { isCardMode = true; deleteCard(); displayCard(); }
    else if (key == 'D' && isCardMode) {
      restoreDefaultDisplay();  // ← SẠCH HOÀN TOÀN
    }
  }

  // === 6. KÍCH HOẠT MÃ TẠM (PHÍM D) ===
  else if (key == 'D') {
    isTempCodeMode = true;
    tempCodeInput = "";
    clearLine(2); lcd.print("CODE(ID:");
    lcd.print(YOUR_LOCK_ID.substring(0, 8)); lcd.print(")");
    clearLine(3); lcd.print("Enter 6 digits #OK");
    clearInputLine();
    Serial.println("[TEMP_CODE] Mode ON - ID: " + YOUR_LOCK_ID);
  }
}

// =================================================================
// Firebase Temp Code -> SỬA LẠI ĐỂ GỌI NODEJS API
bool verifyTempCodeWithServer(String code) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[TEMP_CODE] WiFi not connected");
    return false;
  }

  HTTPClient http;
  // GỌI ĐẾN NODEJS BACKEND THAY VÌ FIREBASE
  String url = String(BACKEND_URL) + "/api/verify-temp-code";
  
  Serial.println("[TEMP_CODE] Verifying with backend: " + url);
  Serial.println("[TEMP_CODE] Code: " + code);
  Serial.println("[TEMP_CODE] Lock ID: " + YOUR_LOCK_ID);
  
  http.begin(url);
  http.setTimeout(10000);
  http.addHeader("Content-Type", "application/json");
  
  // Tạo JSON payload
  String payload = "{\"code\":\"" + code + "\",\"lockId\":\"" + YOUR_LOCK_ID + "\"}";
  Serial.println("[TEMP_CODE] Payload: " + payload);
  
  int httpCode = http.POST(payload);
  Serial.println("[TEMP_CODE] Response code: " + String(httpCode));

  bool isValid = false;
  if (httpCode == 200) {
    String response = http.getString();
    Serial.println("[TEMP_CODE] Response body: " + response);
    
    // Parse JSON response từ NodeJS
    // Expected: {"success":true,"valid":true,...}
    if (response.indexOf("\"valid\":true") > 0 && response.indexOf("\"success\":true") > 0) {
      isValid = true;
      Serial.println("[TEMP_CODE] ✅ Code is VALID");
    } else {
      Serial.println("[TEMP_CODE] ❌ Code is INVALID");
      // Log lý do từ server
      if (response.indexOf("\"message\"") > 0) {
        int msgStart = response.indexOf("\"message\":\"") + 11;
        int msgEnd = response.indexOf("\"", msgStart);
        String message = response.substring(msgStart, msgEnd);
        Serial.println("[TEMP_CODE] Reason: " + message);
      }
    }
  } else if (httpCode < 0) {
    Serial.println("[TEMP_CODE] ❌ Connection error: " + http.errorToString(httpCode));
  } else {
    Serial.println("[TEMP_CODE] ❌ Server error: " + String(httpCode));
  }
  
  http.end();
  return isValid;
}