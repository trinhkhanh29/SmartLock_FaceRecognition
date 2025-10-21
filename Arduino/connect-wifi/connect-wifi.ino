#include <WiFi.h>
#include <WebServer.h>
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

// --- Khởi tạo các đối tượng và biến toàn cục ---
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
LiquidCrystal_I2C lcd(0x27, 20, 4);
WebServer server(80);
MFRC522 rfid(SS_PIN, RST_PIN);
Preferences preferences;

// Biến trạng thái
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

// =================================================================
// *** KHAI BÁO NGUYÊN MẪU HÀM (FUNCTION PROTOTYPES) ĐỂ SỬA LỖI ***
// =================================================================
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
// =================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ; // Chờ kết nối Serial
  }
  Serial.println("ESP32 Serial Initialized");
  Wire.begin(15, 16);

  if (!checkLCD()) {
    Serial.println("Warning: LCD not responding.");
  }
  lcd.init();
  lcd.begin(20, 4);
  lcd.backlight();
  delay(100);

  loadDataFromFlash();

  lcd.setCursor(0, 0);
  lcd.print("DOOR CLOSED");
  lcd.setCursor(0, 1);
  lcd.print("PIN: ");
  lcd.setCursor(0, 2);
  lcd.print("SYSTEM READY");
  lcd.setCursor(0, 3);
  lcd.print("IP: ");

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  WiFi.begin(ssid, password);
  Serial.println("Connecting to WiFi...");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    String ip = WiFi.localIP().toString();
    Serial.println("\nWiFi connected, IP: " + ip);
    lcd.setCursor(4, 3);
    lcd.print(ip);
  } else {
    Serial.println("\nFailed to connect to WiFi.");
    lcd.setCursor(0, 2);
    lcd.print("WIFI ERROR     ");
    while (true);
  }
  
  // Web Server Routes với bảo mật API Key
  server.on("/SUCCESS", []() {
    String apiKey = "28280303";
    if (server.hasArg("key") && server.arg("key") == apiKey) {
        openDoor();
        server.send(200, "text/plain", "Door opened");
    } else {
        server.send(401, "text/plain", "Unauthorized");
    }
  });

  server.on("/FAIL", []() {
    Serial.println("Recognition failed - Turn on red LED");
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);
    lcd.setCursor(0, 2);
    lcd.print("ACCESS DENIED  ");
    delay(2000);
    digitalWrite(RED_LED_PIN, LOW);
    lcd.setCursor(0, 2);
    lcd.print("               ");
    server.send(200, "text/plain", "Access denied");
  });

  server.on("/CLOSE", []() {
    closeDoor();
    server.send(200, "text/plain", "Door closed");
  });
  
  server.begin();
  Serial.println("WebServer started on port 80");

  SPI.begin();
  rfid.PCD_Init();
  Serial.println("RFID ready...");

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  closeDoor();

  lcd.setCursor(0, 2);
  lcd.print("               ");
}

void loop() {
  server.handleClient();

  // Xử lý lệnh từ Serial
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    Serial.println("[LOG] Nhận lệnh Serial: " + command);
    if (command == "SUCCESS") {
      openDoor();
      Serial.println("Door opened via Serial");
    } else if (command == "FAIL") {
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      lcd.setCursor(0, 2);
      lcd.print("ACCESS DENIED  ");
      Serial.println("Access denied via Serial");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      lcd.setCursor(0, 2);
      lcd.print("               ");
    }
  }

  unsigned long currentTime = millis();
  if (obstacleDetected) {
    if (currentTime - lastDistanceMeasureTime >= activeMeasureInterval) {
      measureDistance();
      lastDistanceMeasureTime = currentTime;
    }
  } else {
    if (currentTime - lastDistanceMeasureTime >= idleMeasureInterval) {
      measureDistance();
      lastDistanceMeasureTime = currentTime;
    }
  }

  if (!isCardMode && rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String cardUID = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      cardUID += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
      cardUID += String(rfid.uid.uidByte[i], HEX);
    }
    cardUID.toUpperCase();
    Serial.println("UID: " + cardUID);

    bool isAuthorized = false;
    for (int i = 0; i < numAuthorizedUIDs; i++) {
      if (authorizedUIDs[i] == cardUID) {
        isAuthorized = true;
        break;
      }
    }

    if (isAuthorized) {
      openDoor();
      lcd.setCursor(0, 2);
      lcd.print("OPEN BY RFID   ");
    } else {
      digitalWrite(RED_LED_PIN, HIGH);
      lcd.setCursor(0, 2);
      lcd.print("INVALID CARD   ");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      lcd.setCursor(0, 2);
      lcd.print("               ");
    }
    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(500);
  }
  
  char key = keypad.getKey();
  if (key) {
    if (key == '#') {
      if (changePinMode) {
        if (newPin.length() == 4) {
          savePinToFlash(newPin);
          lcd.setCursor(0, 2);
          lcd.print("PIN CHANGE OK  ");
          digitalWrite(GREEN_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(GREEN_LED_PIN, LOW);
        } else {
          lcd.setCursor(0, 2);
          lcd.print("PIN MUST BE 4  ");
          digitalWrite(RED_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(RED_LED_PIN, LOW);
        }
        changePinMode = false;
        newPin = "";
        inputPin = "";
        pinValidated = false;
        lcd.setCursor(0, 2);
        lcd.print("               ");
        lcd.setCursor(5, 1);
        lcd.print("    ");
      } else {
        if (inputPin == currentPin) {
          pinValidated = true;
          openDoor();
          lcd.setCursor(0, 2);
          lcd.print("OPEN BY PIN    ");
        } else {
          lcd.setCursor(0, 2);
          lcd.print("WRONG PIN      ");
          digitalWrite(RED_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(RED_LED_PIN, LOW);
          pinValidated = false;
        }
        inputPin = "";
        lcd.setCursor(5, 1);
        lcd.print("    ");
        delay(1000);
        lcd.setCursor(0, 2);
        lcd.print("               ");
      }
      isCardMode = false;
    } 
    else if (key == '*') {
      if (!changePinMode && pinValidated) {
        changePinMode = true;
        newPin = "";
        inputPin = "";
        lcd.setCursor(0, 2);
        lcd.print("ENTER NEW PIN  ");
        lcd.setCursor(5, 1);
        lcd.print("    ");
      } else {
        lcd.setCursor(0, 2);
        lcd.print("WRONG PIN/DENIED");
        digitalWrite(RED_LED_PIN, HIGH);
        delay(2000);
        digitalWrite(RED_LED_PIN, LOW);
        lcd.setCursor(0, 2);
        lcd.print("               ");
      }
      isCardMode = false;
    } 
    else if (key >= '0' && key <= '9') {
      if (changePinMode) {
        if (newPin.length() < 4) {
          newPin += key;
          lcd.setCursor(5, 1);
          lcd.print(newPin);
        }
      } else {
        if (inputPin.length() < 4) {
          inputPin += key;
          lcd.setCursor(5, 1);
          lcd.print(inputPin);
        }
      }
      isCardMode = false;
    } else if (pinValidated) {
      if (key == 'A') {
        isCardMode = true;
        currentCardIndex = 0;
        displayCard();
      } else if (key == 'B') {
        isCardMode = true;
        addCard();
        displayCard();
      } else if (key == 'C') {
        isCardMode = true;
        deleteCard();
        displayCard();
      } else if (key == 'D' && isCardMode) {
        isCardMode = false;
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print(doorIsOpen ? "DOOR OPEN      " : "DOOR CLOSED    ");
        lcd.setCursor(0, 1);
        lcd.print("PIN: ");
        lcd.setCursor(0, 3);
        lcd.print("IP: ");
        lcd.print(WiFi.localIP().toString());
      }
    }
  }

  if (doorIsOpen && (millis() - doorOpenTime >= doorOpenDuration)) {
    closeDoor();
  }
  delay(100);
}

// =================================================================
// *** ĐỊNH NGHĨA CHI TIẾT CÁC HÀM ***
// =================================================================

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
  Serial.println("--- Data Loaded From Flash ---");
  Serial.println("PIN: " + currentPin);
  Serial.println("UID Count: " + String(numAuthorizedUIDs));
  for(int i=0; i<numAuthorizedUIDs; i++){
    Serial.println("UID " + String(i) + ": " + authorizedUIDs[i]);
  }
  Serial.println("----------------------------");
}

void savePinToFlash(String pinToSave) {
  preferences.begin("smartlock", false);
  preferences.putString("pin", pinToSave);
  preferences.end();
  currentPin = pinToSave;
  Serial.println("PIN saved to flash: " + pinToSave);
}

void saveUIDsToFlash() {
  preferences.begin("smartlock", false);
  preferences.putInt("uid_count", numAuthorizedUIDs);
  for (int i = 0; i < numAuthorizedUIDs; i++) {
    String key = "uid_" + String(i);
    preferences.putString(key.c_str(), authorizedUIDs[i]);
  }
  for (int i = numAuthorizedUIDs; i < MAX_UIDS; i++) {
     String key = "uid_" + String(i);
     if (preferences.isKey(key.c_str())) {
        preferences.remove(key.c_str());
     }
  }
  preferences.end();
  Serial.println("UID list saved to flash.");
}

void addCard() {
  lcd.setCursor(0, 2);
  lcd.print("SCAN NEW CARD  ");
  lcd.setCursor(0, 3);
  lcd.print("               ");

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
          lcd.setCursor(0, 2);
          lcd.print("CARD EXISTS    ");
          delay(2000);
          rfid.PICC_HaltA();
          rfid.PCD_StopCrypto1();
          return;
        }
      }

      if (numAuthorizedUIDs < MAX_UIDS) {
        authorizedUIDs[numAuthorizedUIDs] = cardUID;
        numAuthorizedUIDs++;
        saveUIDsToFlash();
        lcd.setCursor(0, 2);
        lcd.print("CARD ADDED     ");
      } else {
        lcd.setCursor(0, 2);
        lcd.print("CARD LIST FULL ");
      }
      delay(2000);
      rfid.PICC_HaltA();
      rfid.PCD_StopCrypto1();
      return;
    }
  }
  lcd.setCursor(0, 2);
  lcd.print("TIMEOUT        ");
  delay(2000);
}

void deleteCard() {
  if (numAuthorizedUIDs == 0) {
    lcd.setCursor(0, 2);
    lcd.print("NO CARDS       ");
    delay(2000);
    return;
  }
  lcd.setCursor(0, 2);
  lcd.print("DELETE CARD ");
  lcd.print(currentCardIndex + 1);
  lcd.print("?");
  lcd.setCursor(0, 3);
  lcd.print("1: YES  2: NO  ");

  unsigned long startTime = millis();
  while (millis() - startTime < 5000) {
    char confirmKey = keypad.getKey();
    if (confirmKey) {
      if (confirmKey == '1') {
        for (int i = currentCardIndex; i < numAuthorizedUIDs - 1; i++) {
          authorizedUIDs[i] = authorizedUIDs[i + 1];
        }
        authorizedUIDs[numAuthorizedUIDs - 1] = "";
        numAuthorizedUIDs--;
        saveUIDsToFlash();
        if (currentCardIndex >= numAuthorizedUIDs && currentCardIndex > 0) {
          currentCardIndex--;
        }
        lcd.setCursor(0, 2);
        lcd.print("CARD DELETED   ");
        delay(2000);
        return;
      } else if (confirmKey == '2') {
        lcd.setCursor(0, 2);
        lcd.print("CANCELLED      ");
        delay(2000);
        return;
      }
    }
  }
  lcd.setCursor(0, 2);
  lcd.print("TIMEOUT        ");
  delay(2000);
}

void openDoor() {
  if (doorIsOpen) {
    doorOpenTime = millis();
    return;
  }
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(RELAY_PIN, HIGH);
  doorIsOpen = true;
  doorOpenTime = millis();
  Serial.println("Door OPENED");
  lcd.setCursor(0, 0);
  lcd.print("DOOR OPEN      ");
}

void closeDoor() {
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);
  doorIsOpen = false;
  pinValidated = false;
  Serial.println("Door CLOSED");
  lcd.setCursor(0, 0);
  lcd.print("DOOR CLOSED    ");
}

bool checkLCD() {
  Wire.beginTransmission(0x27);
  int error = Wire.endTransmission();
  return (error == 0);
}

void displayCard() {
  if (numAuthorizedUIDs == 0) {
    lcd.setCursor(0, 2);
    lcd.print("NO CARDS       ");
    lcd.setCursor(0, 3);
    lcd.print("               ");
    return;
  }
  // Di chuyển tới thẻ tiếp theo hoặc quay vòng
  if (keypad.getKey() == 'A') {
      currentCardIndex++;
      if(currentCardIndex >= numAuthorizedUIDs) {
        currentCardIndex = 0;
      }
  }
  lcd.setCursor(0, 2);
  lcd.print("CARD ");
  lcd.print(currentCardIndex + 1);
  lcd.print("/");
  lcd.print(numAuthorizedUIDs);
  lcd.print("      ");
  lcd.setCursor(0, 3);
  lcd.print(authorizedUIDs[currentCardIndex] + "          ");
}

void measureDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH, 30000); // Tăng timeout lên 30ms (~5m)
  distance = duration * 0.034 / 2;

  // Log thêm để debug
  Serial.print("Duration: ");
  Serial.print(duration);
  Serial.print(" us, Distance: ");
  Serial.print(distance, 1);
  Serial.println(" cm");

  // Gửi khoảng cách qua Serial
  if (distance > 0 && distance < 400) {
      Serial.println("DISTANCE:" + String(distance, 1) + " cm");
      obstacleDetected = (distance < obstacleThreshold);
  } else {
      Serial.println("DISTANCE:OUT_RANGE");
      obstacleDetected = false;
  }

  if (!changePinMode && !pinValidated && !isCardMode) {
    if (distance > 0 && distance < 400) {
      lcd.setCursor(0, 2);
      lcd.print("DIST: ");
      lcd.print(distance, 0); // Hiển thị số nguyên
      lcd.print(" cm      ");
      obstacleDetected = (distance < obstacleThreshold);
    } else {
      lcd.setCursor(0, 2);
      lcd.print("DIST: OUT RANGE");
      obstacleDetected = false;
    }
  }
}