#include <ArduinoBLE.h>

static const char *target = "XOSS";
static const char *serviceUuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
static const char *controlUuid = "6e400004-b5a3-f393-e0a9-e50e24dcca9e";
static const char *txUuid = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";
static const char *rxUuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";

void printHex(const uint8_t *data, int length) {
  for (int i = 0; i < length; ++i) {
    if (data[i] < 16) Serial.print('0');
    Serial.print(data[i], HEX);
    Serial.print(i + 1 == length ? '\n' : ' ');
  }
}

void setup() {
  Serial.begin(115200);
  unsigned long started = millis();
  while (!Serial && millis() - started < 4000) {}
  Serial.println("XOSS UNO R4 WiFi scanner");
  if (!BLE.begin()) {
    Serial.println("ERROR: BLE bridge did not start");
    while (true) delay(1000);
  }
  BLE.setLocalName("XOSS-probe");
  Serial.println("Scanning for XOSS...");
  BLE.scan();
}

void loop() {
  BLEDevice device = BLE.available();
  if (!device) return;

  String name = device.localName();
  Serial.print("Found: ");
  Serial.print(name);
  Serial.print(" ");
  Serial.println(device.address());
  if (name.indexOf(target) < 0) return;

  BLE.stopScan();
  Serial.println("Connecting...");
  if (!device.connect()) {
    Serial.println("Connection failed");
    BLE.scan();
    return;
  }
  Serial.println("Connected");
  if (!device.discoverAttributes()) {
    Serial.println("GATT discovery failed");
    device.disconnect();
    BLE.scan();
    return;
  }

  BLEService service = device.service(serviceUuid);
  BLECharacteristic ctl = device.characteristic(controlUuid);
  BLECharacteristic tx = device.characteristic(txUuid);
  BLECharacteristic rx = device.characteristic(rxUuid);
  if (!service || !ctl || !tx || !rx) {
    Serial.println("Expected XOSS service/characteristics missing");
    device.disconnect();
    BLE.scan();
    return;
  }
  tx.subscribe();
  ctl.subscribe();
  Serial.println("GATT ready; sending read-only status and disk-space requests");
  uint8_t status[] = {0xff, 0x00, 0xff};
  uint8_t disk[] = {0x09, 0x00, 0x09};
  ctl.writeValue(status, sizeof(status));
  delay(1000);
  ctl.writeValue(disk, sizeof(disk));

  unsigned long until = millis() + 5000;
  while (millis() < until) {
    if (ctl.valueUpdated()) {
      uint8_t data[64];
      int length = ctl.readValue(data, sizeof(data));
      Serial.print("CTL: ");
      printHex(data, length);
    }
    if (tx.valueUpdated()) {
      uint8_t data[64];
      int length = tx.readValue(data, sizeof(data));
      Serial.print("TX: ");
      printHex(data, length);
    }
    delay(10);
  }
  device.disconnect();
  Serial.println("Disconnected; stopping after one probe");
  while (true) delay(1000);
}
