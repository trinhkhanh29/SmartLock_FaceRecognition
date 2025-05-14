#define GREEN_LED_PIN 15  // GPIO 15 cho LED xanh (đúng)
#define RED_LED_PIN 16    // GPIO 16 cho LED đỏ (sai)

void setup() {
  Serial.begin(115200);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(RED_LED_PIN, OUTPUT);
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(RED_LED_PIN, LOW);
  Serial.println("ESP32 sẵn sàng nhận tín hiệu từ Python...");
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "SUCCESS") {
      Serial.println("Nhận diện đúng - Bật LED xanh");
      digitalWrite(GREEN_LED_PIN, HIGH);
      digitalWrite(RED_LED_PIN, LOW);
      delay(2000);
      digitalWrite(GREEN_LED_PIN, LOW);
    }
    else if (command == "FAIL") {
      Serial.println("Nhận diện sai - Bật LED đỏ");
      digitalWrite(GREEN_LED_PIN, LOW);
      digitalWrite(RED_LED_PIN, HIGH);
      delay(2000);
      digitalWrite(RED_LED_PIN, LOW);
    }
  }
}
