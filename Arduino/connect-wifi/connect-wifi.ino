#define GREEN_LED_PIN 15
#define RED_LED_PIN 16
#define RELAY_PIN 5

unsigned long doorOpenTime = 0;
const unsigned long doorOpenDuration = 5000; // 5 giây
bool doorIsOpen = false;

void setup() {
  Serial.begin(115200);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  closeDoor();
  Serial.println("ESP32 sẵn sàng nhận tín hiệu từ Python...");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    Serial.println("Lệnh nhận được: " + command + ", Trạng thái cửa: " + String(doorIsOpen ? "Mở" : "Đóng"));

    if (command == "SUCCESS") {
      openDoor();
    }
    else if (command == "FAIL") {
      Serial.println("Nhận diện thất bại - Bật LED đỏ");
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
    }
    else if (command == "CLOSE") {
      closeDoor();
    }
  }

  if (doorIsOpen) {
    Serial.print("Thời gian mở cửa: ");
    Serial.println(millis() - doorOpenTime);
    
    if (millis() - doorOpenTime >= doorOpenDuration) {
      Serial.println("Tự động đóng cửa sau 5 giây!");
      closeDoor();
    }
  }
  
  delay(100); // Giảm nhiễu
}

void openDoor() {
    Serial.println("Nhận diện thành công - MỞ cửa");
    digitalWrite(GREEN_LED_PIN, HIGH);
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(RELAY_PIN, HIGH); // Thử HIGH để kích hoạt relay
    doorIsOpen = true;
    doorOpenTime = millis();
}

void closeDoor() {
    Serial.println("Đóng cửa");
    digitalWrite(RELAY_PIN, LOW); // Thử LOW để tắt relay
    digitalWrite(GREEN_LED_PIN, LOW);
    doorIsOpen = false;
}