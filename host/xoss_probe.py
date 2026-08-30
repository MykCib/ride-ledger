#!/usr/bin/env python3
import asyncio
import sys
from bleak import BleakClient, BleakScanner

SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
CONTROL = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"

async def main(target):
    print(f"Scanning for {target!r}...")
    devices = await BleakScanner.discover(timeout=15)
    device = next((d for d in devices if target.lower() in (d.name or '').lower()), None)
    if not device:
        print("XOSS device not found")
        for d in devices:
            if d.name:
                print(f"  {d.name} {d.address}")
        return 2
    print(f"Found {device.name} at {device.address}")
    async with BleakClient(device, timeout=30) as client:
        print(f"Connected, MTU={getattr(client, 'mtu_size', 'unknown')}")
        for service in client.services:
            print(f"SERVICE {service.uuid}")
            for characteristic in service.characteristics:
                print(f"  CHAR {characteristic.uuid} {','.join(characteristic.properties)}")

        def notification(sender, data):
            print(f"NOTIFY {sender}: {data.hex(' ')}")

        await client.start_notify(CONTROL, notification)
        await client.start_notify(TX, notification)
        print("Sending status FF 00 FF")
        await client.write_gatt_char(CONTROL, bytes.fromhex("ff 00 ff"), response=False)
        await asyncio.sleep(1)
        print("Sending disk-space request 09 00 09")
        await client.write_gatt_char(CONTROL, bytes.fromhex("09 00 09"), response=False)
        await asyncio.sleep(4)
    return 0

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "XOSS"
    raise SystemExit(asyncio.run(main(name)))
