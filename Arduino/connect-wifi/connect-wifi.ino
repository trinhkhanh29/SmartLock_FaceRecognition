#include <WiFi.h>
#include <WebServer.h>
#include <SPI.h>
#include <MFRC522.h>

const char* ssid = "27 Nhan Hoa ";
const char* password = "22227777";

// Định nghĩa chân cho RFID RC522
#define RST_PIN 22
#define SS_PIN 21

// Định nghĩa chân thiết bị
#define GREEN_LED_PIN 15
#define RED_LED_PIN 16
#define RELAY_PIN 5

WebServer server(80);

// Khởi tạo RFID
MFRC522 rfid(SS_PIN, RST_PIN);

// Thời gian mở cửa
unsigned long doorOpenTime = 0;
const unsigned long doorOpenDuration = 5000; // 5 giây
bool doorIsOpen = false;

// UID thẻ hợp lệ
String authorizedUID = "C35A0905";

void setup() {
  Serial.begin(115200);

  // Kết nối WiFi
  WiFi.begin(ssid, password);
  Serial.println("Đang kết nối WiFi...");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) { // Thử kết nối tối đa 30 lần
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi đã kết nối, IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\nKhông thể kết nối WiFi. Vui lòng kiểm tra SSID và mật khẩu.");
    while (true); // Dừng chương trình nếu không kết nối được
  }

  // Web routes
  server.on("/", []() {
    server.send(200, "text/plain", "ESP32 SmartLock is online");
  });

  server.on("/SUCCESS", []() {
    openDoor();
    server.send(200, "text/plain", "Cửa đã mở");
  });

  server.on("/FAIL", []() {
    Serial.println("Nhận diện thất bại - Bật LED đỏ");
    digitalWrite(GREEN_LED_PIN, LOW);
    digitalWrite(RED_LED_PIN, HIGH);
    delay(2000);
    digitalWrite(RED_LED_PIN, LOW);
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
}

void loop() {
  server.handleClient(); // Xử lý request HTTP

  // RFID check
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
    } else {
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
    }

    rfid.PICC_HaltA();
    rfid.PCD_StopCrypto1();
    delay(500);
  }

  // Tự động đóng cửa sau 5s
  if (doorIsOpen && (millis() - doorOpenTime >= doorOpenDuration)) {
    closeDoor();
  }

  delay(100);
}

void openDoor() {
  if (doorIsOpen) {
    doorOpenTime = millis(); // Gia hạn
    return;
  }
  digitalWrite(GREEN_LED_PIN, HIGH);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(RELAY_PIN, HIGH);
  doorIsOpen = true;
  doorOpenTime = millis();
  Serial.println("Cửa đã MỞ");
}

void closeDoor() {
  digitalWrite(RELAY_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);
  doorIsOpen = false;
  Serial.println("Cửa đã ĐÓNG");
}