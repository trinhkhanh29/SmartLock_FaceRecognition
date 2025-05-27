#include <WiFi.h>
#include <WebServer.h>
#include <SPI.h>
#include <MFRC522.h>
#include <Keypad.h>
#include <LiquidCrystal_I2C.h>
#include <Wire.h>

const char* ssid = "27 Nhan Hoa ";
const char* password = "22227777";

// Định nghĩa chân cho RFID RC522
#define RST_PIN 22
#define SS_PIN 21

// Định nghĩa chân thiết bị (giữ lại LED)
#define GREEN_LED_PIN 0  // G0
#define RED_LED_PIN 2    // G2
#define RELAY_PIN 5

// Định nghĩa chân cho SRF05
#define TRIG_PIN 13  // G13
#define ECHO_PIN 27  // G27

// Định nghĩa chân cho bàn phím
const byte ROWS = 4;
const byte COLS = 4;
char keys[ROWS][COLS] = {
  {'1', '2', '3', 'A'},
  {'4', '5', '6', 'B'},
  {'7', '8', '9', 'C'},
  {'*', '0', '#', 'D'}
};
byte rowPins[ROWS] = {17, 4, 14, 12}; // R1, R2, R3, R4 (G17, G4, G14, G12)
byte colPins[COLS] = {25, 26, 32, 33}; // C1, C2, C3, C4 (G25, G26, G32, G33)

// Khởi tạo bàn phím
Keypad keypad = Keypad(makeKeymap(keys), rowPins, colPins, ROWS, COLS);

// Khởi tạo LCD I2C
LiquidCrystal_I2C lcd(0x27, 20, 4);

// Khởi tạo WebServer và RFID
WebServer server(80);
MFRC522 rfid(SS_PIN, RST_PIN);

// Thời gian mở cửa
unsigned long doorOpenTime = 0;
const unsigned long doorOpenDuration = 5000; // 5 giây
bool doorIsOpen = false;

// UID thẻ hợp lệ
String authorizedUID = "C35A0905";

// Mã PIN mặc định và biến lưu mã PIN hiện tại
String defaultPin = "1234";
String currentPin = defaultPin;
String inputPin = "";
bool changePinMode = false;
String newPin = "";

// Biến để lưu khoảng cách
float distance = 0;

void setup() {
  Serial.begin(115200);

  // Khởi tạo I2C
  Wire.begin(15, 16); // SDA = G15, SCL = G16

  // Khởi tạo LCD
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("CUA DONG");
  lcd.setCursor(0, 1);
  lcd.print("PIN: ");
  lcd.setCursor(0, 2);
  lcd.print("DANG KHOI DONG...");
  lcd.setCursor(0, 3);
  lcd.print("IP: ");

  // Khởi tạo chân cho SRF05
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // In các chân để gỡ lỗi
  Serial.println("Row pins: " + String(rowPins[0]) + ", " + String(rowPins[1]) + ", " + String(rowPins[2]) + ", " + String(rowPins[3]));
  Serial.println("Col pins: " + String(colPins[0]) + ", " + String(colPins[1]) + ", " + String(colPins[2]) + ", " + String(colPins[3]));

  // Kết nối WiFi
  WiFi.begin(ssid, password);
  Serial.println("Đang kết nối WiFi...");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    String ip = WiFi.localIP().toString();
    Serial.println("\nWiFi đã kết nối, IP: " + ip);
    lcd.setCursor(4, 3);
    lcd.print(ip);
  } else {
    Serial.println("\nKhông thể kết nối WiFi. Vui lòng kiểm tra SSID và mật khẩu.");
    lcd.setCursor(0, 2);
    lcd.print("LOI WIFI        ");
    while (true);
  }

  // Web routes
  server.on("/", []() {
    server.send(200, "text/plain", "ESP32 SmartLock đang hoạt động");
  });

  server.on("/SUCCESS", []() {
    openDoor();
    server.send(200, "text/plain", "Cửa đã mở");
  });

  server.on("/FAIL", []() {
    Serial.println("Nhận diện thất bại - Bật LED đỏ");
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);
    lcd.setCursor(0, 2);
    lcd.print("TRUY CAP TU CHOI");
    delay(2000);
    digitalWrite(RED_LED_PIN, LOW);
    lcd.setCursor(0, 2);
    lcd.print("                ");
    server.send(200, "text/plain", "Truy cập bị từ chối");
  });

  server.on("/CLOSE", []() {
    closeDoor();
    server.send(200, "text/plain", "Cửa đã đóng");
  });

  server.begin();
  Serial.println("WebServer khởi động tại cổng 80");

  // Khởi tạo RFID và GPIO
  SPI.begin();
  rfid.PCD_Init();
  Serial.println("RFID sẵn sàng...");

  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  closeDoor();

  // Cập nhật thông báo khởi động xong
  lcd.setCursor(0, 2);
  lcd.print("                ");
}

void loop() {
  server.handleClient();

  // Đo khoảng cách với SRF05
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long duration = pulseIn(ECHO_PIN, HIGH);
  distance = duration * 0.034 / 2; // Tính khoảng cách (cm)
  
  if (distance > 0 && distance < 400) { // SRF05 đo được từ 2cm đến 400cm
    Serial.print("Khoang cach: ");
    Serial.print(distance);
    Serial.println(" cm");
    lcd.setCursor(0, 2);
    lcd.print("KC: ");
    lcd.print(distance);
    lcd.print(" cm          ");
  } else {
    Serial.println("Khoang cach: Out of range");
    lcd.setCursor(0, 2);
    lcd.print("KC: Out of range");
  }

  // Kiểm tra RFID
  if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
    String cardUID = "";
    for (byte i = 0; i < rfid.uid.size; i++) {
      cardUID += String(rfid.uid.uidByte[i] < 0x10 ? "0" : "");
      cardUID += String(rfid.uid.uidByte[i], HEX);
    }
    cardUID.toUpperCase();
    Serial.println("UID: " + cardUID);

    if (cardUID == authorizedUID) {
      openDoor();
      lcd.setCursor(0, 2);
      lcd.print("MO CUA RFID     ");
    } else {
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      lcd.setCursor(0, 2);
      lcd.print("THE KHONG HOP LE");
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
      lcd.setCursor(0, 2);
      lcd.print("                ");
    }

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(500);
  }

  // Kiểm tra bàn phím
  char key = keypad.getKey();
  if (key) {
    Serial.println("Phím bấm: " + String(key));

    if (key == '#') {
      if (changePinMode) {
        if (newPin.length() == 4) {
          currentPin = newPin;
          Serial.println("Mã PIN đã được đổi thành: " + currentPin);
          lcd.setCursor(0, 2);
          lcd.print("DOI PIN THANH CONG");
          changePinMode = false;
          newPin = "";
          digitalWrite(GREEN_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(GREEN_LED_PIN, LOW);
          lcd.setCursor(0, 2);
          lcd.print("                  ");
        } else {
          Serial.println("Mã PIN mới phải có 4 chữ số!");
          lcd.setCursor(0, 2);
          lcd.print("PIN MOI PHAI 4 SO");
          changePinMode = false;
          newPin = "";
          digitalWrite(RED_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(RED_LED_PIN, LOW);
          lcd.setCursor(0, 2);
          lcd.print("                 ");
        }
      } else {
        if (inputPin == currentPin) {
          openDoor();
          lcd.setCursor(0, 2);
          lcd.print("MO CUA PIN      ");
        } else {
          Serial.println("Mã PIN sai!");
          lcd.setCursor(0, 2);
          lcd.print("MA PIN SAI      ");
          digitalWrite(GREEN_LED_PIN, LOW);
          digitalWrite(RED_LED_PIN, HIGH);
          delay(2000);
          digitalWrite(RED_LED_PIN, LOW);
          lcd.setCursor(0, 2);
          lcd.print("                ");
        }
      }
      inputPin = "";
      lcd.setCursor(5, 1);
      lcd.print("    ");
    } else if (key == '*') {
      if (inputPin == currentPin) {
        changePinMode = true;
        newPin = "";
        Serial.println("Nhập mã PIN mới (4 chữ số), sau đó nhấn #:");
        lcd.setCursor(0, 2);
        lcd.print("NHAP PIN MOI    ");
      } else {
        Serial.println("MÃ PIN sai, không thể đổi!");
        lcd.setCursor(0, 2);
        lcd.print("MA PIN SAI      ");
        digitalWrite(RED_LED_PIN, HIGH);
        delay(2000);
        digitalWrite(RED_LED_PIN, LOW);
        lcd.setCursor(0, 2);
        lcd.print("                ");
      }
      inputPin = "";
      lcd.setCursor(5, 1);
      lcd.print("    ");
    } else if (key >= '0' && key <= '9') {
      if (changePinMode) {
        if (newPin.length() < 4) {
          newPin += key;
          Serial.println("Mã PIN mới đang nhập: " + newPin);
          lcd.setCursor(5, 1);
          lcd.print(newPin);
        }
      } else {
        if (inputPin.length() < 4) {
          inputPin += key;
          Serial.println("Mã PIN đang nhập: " + inputPin);
          lcd.setCursor(5, 1);
          lcd.print(inputPin);
        }
      }
    }
  }

  // Tự động đóng cửa sau 5 giây
  if (doorIsOpen && (millis() - doorOpenTime >= doorOpenDuration)) {
    closeDoor();
  }

  delay(100);
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
  Serial.println("Cửa đã MỞ");
  lcd.setCursor(0, 0);
  lcd.print("CUA MO          ");
}

void closeDoor() {
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);
  doorIsOpen = false;
  Serial.println("Cửa đã ĐÓNG");
  lcd.setCursor(0, 0);
  lcd.print("CUA DONG        ");
}