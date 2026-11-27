"""Bidirectional serial transport for the tactile hand interface."""

from threading import Lock
import time

import serial

from .contracts import HandInputState


class DeviceSerial:
    """Send tactile frames and receive physical hand controls."""

    OUTPUT_SYNC = 0xFF
    INPUT_SYNC = 0xFE
    INPUT_TYPE = 0x01
    INPUT_PACKET_SIZE = 7

    def __init__(self, port: str, baudrate: int = 115200):
        self.ser = serial.Serial(port, baudrate, timeout=0)
        self.packet = bytearray([self.OUTPUT_SYNC, 0, 0, 0, 0, 0])
        self._input_buffer = bytearray()
        self._input_state = HandInputState()
        self._input_lock = Lock()
        time.sleep(2)

    def set_channel(self, ch: int, val: int) -> None:
        if not (0 <= ch < 20):
            raise ValueError("Channel must be between 0 and 19")
        if val not in (0, 1, 2):
            raise ValueError("Value must be between 0 and 2")
        byte_idx = 1 + (ch >> 2)
        bit_shift = (ch & 0x03) << 1
        self.packet[byte_idx] &= ~(0x03 << bit_shift)
        self.packet[byte_idx] |= (val & 0x03) << bit_shift

    def set_all(self, values: list[int]) -> None:
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
        self.ser.write(self.packet)
        self.ser.flush()

    def poll_input(self) -> None:
        """Decode all available input packets without blocking."""
        data = self.ser.read(self.ser.in_waiting or 1)
        if not data:
            return
        self._input_buffer.extend(data)
        while True:
            try:
                start = self._input_buffer.index(self.INPUT_SYNC)
            except ValueError:
                self._input_buffer.clear()
                return
            if start:
                del self._input_buffer[:start]
            if len(self._input_buffer) < self.INPUT_PACKET_SIZE:
                return
            packet = self._input_buffer[:self.INPUT_PACKET_SIZE]
            if packet[1] != self.INPUT_TYPE:
                del self._input_buffer[0]
                continue
            if (sum(packet[1:6]) & 0xFF) != packet[6]:
                del self._input_buffer[0]
                continue
            del self._input_buffer[:self.INPUT_PACKET_SIZE]
            raw = int.from_bytes(packet[3:5], byteorder="big", signed=True)
            axis = max(-1.0, min(1.0, raw / 1000.0))
            with self._input_lock:
                self._input_state = HandInputState(
                    joystick=axis,
                    button_down=bool(packet[5]),
                    button_pressed=bool(packet[5]),
                )

    def read_input(self) -> HandInputState:
        with self._input_lock:
            return self._input_state

    def close(self) -> None:
        self.ser.close()
