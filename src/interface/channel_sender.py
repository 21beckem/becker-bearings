import serial
import time

class ChannelSender:
    SYNC_BYTE = 0xFF

    def __init__(self, port: str, baudrate: int = 115200):
        self.ser = serial.Serial(port, baudrate, timeout=0.1)
        # Pre-allocate 6-byte packet: [0xFF, data0, data1, data2, data3, data4]
        self.packet = bytearray([self.SYNC_BYTE, 0, 0, 0, 0, 0])
        time.sleep(2)  # Wait for Arduino auto-reset on serial connection

    def set_channel(self, ch: int, val: int) -> None:
        """Set a single channel (0-19) to a value (0, 1, or 2)."""
        if not (0 <= ch < 20):
            raise ValueError("Channel must be between 0 and 19")
        if val not in (0, 1, 2):
            raise ValueError("Value must be 0, 1, or 2")

        byte_idx = 1 + (ch >> 2)        # Offset by 1 for SYNC_BYTE
        bit_shift = (ch & 0x03) << 1    # (ch % 4) * 2

        self.packet[byte_idx] &= ~(0x03 << bit_shift)         # Clear target 2 bits
        self.packet[byte_idx] |= ((val & 0x03) << bit_shift)  # Set new value

    def set_all(self, values: list[int]) -> None:
        """Pack a list/sequence of 20 values (0, 1, or 2) at once."""
        if len(values) != 20:
            raise ValueError("Expected exactly 20 channel values")

        for i in range(5):
            base = i << 2
            self.packet[1 + i] = (
                (values[base] & 0x03)
                | ((values[base + 1] & 0x03) << 2)
                | ((values[base + 2] & 0x03) << 4)
                | ((values[base + 3] & 0x03) << 6)
            )

    def send(self) -> None:
        """Transmit the packet and print any microcontroller debug output."""
        self.ser.write(self.packet)
        self.ser.flush()

        while True:
            line = self.ser.readline()
            if not line:
                break
            print(line.decode("utf-8", errors="replace"), end="", flush=True)

    def close(self) -> None:
        self.ser.close()


# --- Example Usage ---
if __name__ == "__main__":
    sender = ChannelSender(port="COM4", baudrate=115200)

    try:
        while True:
            # # Option 1: Update individual channels
            # sender.set_channel(0, 2)
            # # sender.set_channel(19, 2)
            # sender.send()
            t = 0.1
            time.sleep(t)

            # Option 2: Update all 20 channels from a list in one go
            states = [0, 1, 2, 0] * 5
            sender.set_all(states)
            sender.send()

            time.sleep(t)

            # Option 2: Update all 20 channels from a list in one go
            states = [1, 2, 0, 1] * 5
            sender.set_all(states)
            sender.send()

            time.sleep(t)

            # Option 2: Update all 20 channels from a list in one go
            states = [2, 0, 1, 2] * 5
            sender.set_all(states)
            sender.send()

    finally:
        sender.close()
