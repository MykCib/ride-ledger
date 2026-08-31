#include <ArduinoBLE.h>

static const char TARGET_NAME[] = "XOSS G-933835";
static const char CTL_UUID[] = "6e400004-b5a3-f393-e0a9-e50e24dcca9e";
static const char TX_UUID[] = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";
static const char RX_UUID[] = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";

static const uint8_t VALUE_IDLE[] = {0x04, 0x00, 0x04};
static const uint8_t VALUE_C = 0x43;
static const uint8_t VALUE_ACK = 0x06;
static const uint8_t VALUE_NAK = 0x15;
static const uint8_t VALUE_EOT = 0x04;
static const uint8_t VALUE_CAN = 0x18;

static const uint32_t SCAN_TIMEOUT_MS = 15000;
static const uint32_t NOTIFICATION_TIMEOUT_MS = 10000;
static const size_t MAX_NOTIFICATION_SIZE = 256;
static const size_t MAX_BLOCK_SIZE = 1029;
static const size_t NOTIFICATION_QUEUE_SIZE = 32;

struct Notification {
  uint8_t data[MAX_NOTIFICATION_SIZE];
  size_t length = 0;
};

struct Block {
  uint8_t data[MAX_BLOCK_SIZE];
  size_t length = 0;
  size_t total = 0;
};

BLEDevice xoss;
BLECharacteristic* control = nullptr;
BLECharacteristic* transmit = nullptr;
BLECharacteristic* receive = nullptr;
bool ble_ready = false;
bool xoss_connected = false;
Notification notification_queue[NOTIFICATION_QUEUE_SIZE];
size_t notification_head = 0;
size_t notification_tail = 0;
bool notification_overflow = false;

void disconnect_xoss();

void log_message(const char* message) {
  Serial.print("# ");
  Serial.println(message);
}

uint8_t crc8_xor(const uint8_t* data, size_t length) {
  uint8_t crc = 0;
  for (size_t i = 0; i < length; i++) {
    crc ^= data[i];
  }
  return crc;
}

uint16_t crc16_arc(const uint8_t* data, size_t length) {
  uint16_t crc = 0;
  for (size_t i = 0; i < length; i++) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; bit++) {
      crc = (crc & 1) ? (crc >> 1) ^ 0xa001 : crc >> 1;
    }
  }
  return crc;
}

bool same_bytes(const uint8_t* left, size_t left_length,
                const uint8_t* right, size_t right_length) {
  return left_length == right_length &&
         memcmp(left, right, left_length) == 0;
}

bool valid_filename(const char* filename) {
  size_t length = strlen(filename);
  if (length == 0 || length > 40) {
    return false;
  }
  if (strcmp(filename, "workouts.json") != 0 &&
      (length < 4 || strcmp(filename + length - 4, ".fit") != 0)) {
    return false;
  }
  for (size_t i = 0; i < length; i++) {
    char c = filename[i];
    if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
          (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-')) {
      return false;
    }
  }
  return true;
}

int make_command(uint8_t command, const char* filename, uint8_t* output) {
  size_t filename_length = strlen(filename);
  output[0] = command;
  memcpy(output + 1, filename, filename_length);
  output[filename_length + 1] = crc8_xor(output, filename_length + 1);
  return filename_length + 2;
}

bool write_control(const uint8_t* data, size_t length) {
  return control != nullptr && control->writeValue(data, length, true) != 0;
}

bool write_receive(uint8_t value) {
  return receive != nullptr && receive->writeValue(&value, 1, false) != 0;
}

void clear_notifications() {
  notification_head = 0;
  notification_tail = 0;
  notification_overflow = false;
}

void notification_handler(BLEDevice device, BLECharacteristic characteristic) {
  (void)device;
  if (notification_overflow) {
    return;
  }

  size_t next_tail = (notification_tail + 1) % NOTIFICATION_QUEUE_SIZE;
  if (next_tail == notification_head) {
    notification_overflow = true;
    return;
  }

  Notification& queued = notification_queue[notification_tail];
  queued.length = min((size_t)characteristic.valueLength(), MAX_NOTIFICATION_SIZE);
  memcpy(queued.data, characteristic.value(), queued.length);
  notification_tail = next_tail;
}

bool next_notification(Notification& notification, uint32_t timeout_ms) {
  uint32_t started = millis();
  while (millis() - started < timeout_ms) {
    BLE.poll();

    if (notification_overflow) {
      return false;
    }
    if (notification_head != notification_tail) {
      Notification& queued = notification_queue[notification_head];
      notification.length = queued.length;
      memcpy(notification.data, queued.data, queued.length);
      notification_head = (notification_head + 1) % NOTIFICATION_QUEUE_SIZE;
      return true;
    }
    delay(1);
  }
  return false;
}

bool wait_for_bytes(const uint8_t* expected, size_t length, uint32_t timeout_ms) {
  Notification notification;
  uint32_t started = millis();
  while (millis() - started < timeout_ms) {
    uint32_t remaining = timeout_ms - (millis() - started);
    if (!next_notification(notification, remaining)) {
      return false;
    }
    if (same_bytes(notification.data, notification.length, expected, length)) {
      return true;
    }
  }
  return false;
}

bool get_idle_status() {
  const uint8_t status[] = {0xff, 0x00, 0xff};
  clear_notifications();
  if (!write_control(status, sizeof(status))) {
    log_message("idle status write failed");
    return false;
  }
  delay(100);

  if (wait_for_bytes(VALUE_IDLE, sizeof(VALUE_IDLE), 5000)) {
    return true;
  }
  log_message("idle status response timeout");
  if (!write_control(VALUE_IDLE, sizeof(VALUE_IDLE))) {
    log_message("idle fallback write failed");
    return false;
  }
  delay(100);
  if (!wait_for_bytes(VALUE_IDLE, sizeof(VALUE_IDLE), 5000)) {
    log_message("idle fallback response timeout");
    return false;
  }
  return true;
}

bool read_block(Block& block, bool& eot) {
  block.length = 0;
  block.total = 0;
  eot = false;

  uint32_t started = millis();
  while (millis() - started < NOTIFICATION_TIMEOUT_MS) {
    Notification notification;
    uint32_t remaining = NOTIFICATION_TIMEOUT_MS - (millis() - started);
    if (!next_notification(notification, remaining)) {
      return false;
    }
    if (block.length == 0 && notification.length == 1 &&
        notification.data[0] == VALUE_EOT) {
      eot = true;
      return true;
    }
    if (notification.length == 0) {
      return false;
    }

    if (block.length == 0) {
      if (notification.data[0] != 0x01 && notification.data[0] != 0x02) {
        return false;
      }
      block.total = notification.data[0] == 0x02 ? 1029 : 133;
    }
    if (block.length + notification.length > block.total ||
        block.length + notification.length > MAX_BLOCK_SIZE) {
      return false;
    }
    memcpy(block.data + block.length, notification.data, notification.length);
    block.length += notification.length;
    if (block.length == block.total) {
      if (block.data[2] != (uint8_t)(0xff ^ block.data[1])) {
        return false;
      }
      uint16_t expected = ((uint16_t)block.data[block.total - 2] << 8) |
                          block.data[block.total - 1];
      uint16_t actual = crc16_arc(block.data + 3, block.total - 5);
      return expected == actual;
    }
  }
  return false;
}

bool block_zero_size(const Block& block, uint32_t& size) {
  size_t data_length = block.total - 5;
  char metadata[129];
  size_t copy_length = min(data_length, sizeof(metadata) - 1);
  memcpy(metadata, block.data + 3, copy_length);
  metadata[copy_length] = '\0';

  char* separator = strchr(metadata, ' ');
  if (separator == nullptr || separator == metadata || *(separator + 1) == '\0') {
    return false;
  }
  char* end = nullptr;
  unsigned long parsed = strtoul(separator + 1, &end, 10);
  if (end == separator + 1 || parsed > 0xffffffffUL) {
    return false;
  }
  size = (uint32_t)parsed;
  return true;
}

bool finish_transfer() {
  if (!write_receive(VALUE_NAK)) {
    return false;
  }
  delay(100);
  if (!wait_for_bytes(&VALUE_EOT, 1, 5000)) {
    return false;
  }
  delay(100);
  if (!write_receive(VALUE_ACK)) {
    return false;
  }
  delay(100);
  return wait_for_bytes(VALUE_IDLE, sizeof(VALUE_IDLE), 5000);
}

bool fetch_file(const char* filename) {
  if (!get_idle_status()) {
    return false;
  }

  uint8_t command[64];
  int command_length = make_command(0x05, filename, command);
  if (!write_control(command, command_length)) {
    log_message("file request write failed");
    return false;
  }
  delay(100);

  uint8_t accepted[64];
  int accepted_length = make_command(0x06, filename, accepted);
  if (!wait_for_bytes(accepted, accepted_length, 5000)) {
    log_message("file acceptance timeout");
    return false;
  }

  Block block;
  bool eot = false;
  bool valid_zero = false;
  for (int attempt = 0; attempt < 3 && !valid_zero; attempt++) {
    if (!write_receive(VALUE_C)) {
      log_message("block zero handshake failed");
      return false;
    }
    delay(100);
    valid_zero = read_block(block, eot) && !eot && block.data[1] == 0;
    if (!valid_zero) {
      write_receive(VALUE_NAK);
      delay(100);
    }
  }
  if (!valid_zero) {
    log_message("block zero retries exhausted");
    write_receive(VALUE_CAN);
    return false;
  }

  uint32_t file_size = 0;
  if (!block_zero_size(block, file_size)) {
    log_message("block zero metadata invalid");
    write_receive(VALUE_CAN);
    return false;
  }

  Serial.print("FILE ");
  Serial.print(filename);
  Serial.print(" ");
  Serial.println(file_size);
  Serial.flush();

  if (!write_receive(VALUE_ACK)) {
    log_message("block zero ACK failed");
    return false;
  }
  delay(100);
  if (!write_receive(VALUE_C)) {
    log_message("data handshake failed");
    return false;
  }
  delay(100);

  uint32_t remaining = file_size;
  uint8_t expected_block = 1;
  while (true) {
    bool received = false;
    for (int attempt = 0; attempt < 5 && !received; attempt++) {
      eot = false;
      if (!read_block(block, eot)) {
        write_receive(VALUE_NAK);
        delay(100);
        continue;
      }

      if (eot) {
        received = true;
        break;
      }

      if (block.data[1] == expected_block) {
        size_t data_length = block.total - 5;
        size_t to_send = min((uint32_t)data_length, remaining);
        if (to_send > 0) {
          Serial.write(block.data + 3, to_send);
          remaining -= to_send;
        }
        expected_block++;
        received = true;
      } else if (expected_block != 1 &&
                 block.data[1] == (uint8_t)(expected_block - 1)) {
        // The sender may repeat a block when its previous ACK was lost.
        received = true;
      } else {
        write_receive(VALUE_NAK);
        delay(100);
        continue;
      }

      if (!write_receive(VALUE_ACK)) {
        return false;
      }
      delay(100);
    }
    if (!received) {
      log_message("data block retries exhausted");
      write_receive(VALUE_CAN);
      return false;
    }
    if (eot) {
      break;
    }
  }

  if (remaining != 0 || !finish_transfer()) {
    log_message("file completion failed");
    return false;
  }
  Serial.flush();
  Serial.println("END");
  return true;
}

bool connect_xoss() {
  if (xoss_connected && xoss.connected()) {
    return true;
  }
  xoss_connected = false;

  log_message("scanning for XOSS");
  if (!BLE.scan()) {
    return false;
  }

  uint32_t started = millis();
  bool found = false;
  while (millis() - started < SCAN_TIMEOUT_MS) {
    BLEDevice candidate = BLE.available();
    if (candidate && candidate.hasLocalName() &&
        candidate.localName() == TARGET_NAME) {
      xoss = candidate;
      found = true;
      break;
    }
    delay(10);
  }
  BLE.stopScan();
  if (!found) {
    return false;
  }

  log_message("XOSS found; connecting");
  if (!xoss.connect()) {
    log_message("XOSS connection failed");
    return false;
  }
  xoss_connected = true;
  if (!xoss.discoverAttributes()) {
    log_message("XOSS attribute discovery failed");
    disconnect_xoss();
    return false;
  }
  BLECharacteristic discovered_control = xoss.characteristic(CTL_UUID);
  BLECharacteristic discovered_transmit = xoss.characteristic(TX_UUID);
  BLECharacteristic discovered_receive = xoss.characteristic(RX_UUID);
  control = new BLECharacteristic(discovered_control);
  transmit = new BLECharacteristic(discovered_transmit);
  receive = new BLECharacteristic(discovered_receive);
  if (control == nullptr || transmit == nullptr || receive == nullptr ||
      !*control || !*transmit || !*receive) {
    log_message("XOSS transfer characteristics missing");
    disconnect_xoss();
    return false;
  }
  control->setEventHandler(BLEUpdated, notification_handler);
  transmit->setEventHandler(BLEUpdated, notification_handler);
  if (!control->subscribe() || !transmit->subscribe()) {
    log_message("XOSS notification subscription failed");
    disconnect_xoss();
    return false;
  }
  clear_notifications();
  log_message("XOSS connected");
  return true;
}

void release_characteristics() {
  delete control;
  delete transmit;
  delete receive;
  control = nullptr;
  transmit = nullptr;
  receive = nullptr;
}

void disconnect_xoss() {
  if (xoss_connected) {
    xoss.disconnect();
  }
  release_characteristics();
  clear_notifications();
  xoss_connected = false;
}

void respond_error(const char* message) {
  Serial.print("ERR ");
  Serial.println(message);
}

void handle_command(char* command) {
  size_t length = strlen(command);
  while (length > 0 && (command[length - 1] == '\r' || command[length - 1] == '\n')) {
    command[--length] = '\0';
  }

  if (strcmp(command, "PING") == 0) {
    Serial.println("PONG");
    return;
  }
  if (strcmp(command, "CLOSE") == 0) {
    disconnect_xoss();
    Serial.println("OK");
    return;
  }
  if (strncmp(command, "GET ", 4) != 0 || !valid_filename(command + 4)) {
    respond_error("invalid-command");
    return;
  }
  if (!ble_ready) {
    respond_error("ble-not-ready");
    return;
  }
  if (!connect_xoss()) {
    disconnect_xoss();
    respond_error("xoss-unavailable");
    return;
  }
  if (!fetch_file(command + 4)) {
    disconnect_xoss();
    respond_error("transfer-failed");
  }
}

void setup() {
  Serial.begin(115200);
  delay(100);
  log_message("UNO R4 XOSS bridge starting");
  ble_ready = BLE.begin();
  if (ble_ready) {
    log_message("BLE ready");
  } else {
    log_message("BLE initialization failed");
  }
}

void loop() {
  static char command[64];
  static size_t command_length = 0;

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (command_length > 0) {
        command[command_length] = '\0';
        handle_command(command);
        command_length = 0;
      }
    } else if (command_length < sizeof(command) - 1) {
      command[command_length++] = c;
    } else {
      command_length = 0;
      respond_error("command-too-long");
    }
  }
  delay(1);
}
