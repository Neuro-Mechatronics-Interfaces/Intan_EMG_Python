import socket
import serial
import numpy as np
import collections
from statistics import mode, StatisticsError

class PicoMessager:
    """Class for managing serial communication with a Raspberry Pi Pico."""

    def __init__(self, port='COM13', baudrate=115200, buffer_size=10):
        """Initializes the PicoMessager.
        
        Args:
            port (str): The serial port to connect to (e.g., 'COM13').
            baudrate (int): The baud rate for serial communication.
            buffer_size (int): The number of past gestures to keep in the buffer.
        """
        self.port = port
        self.baudrate = baudrate
        self.buffer = collections.deque(maxlen=buffer_size)
        self.current_gesture = None  # Keep track of the current gesture being sent

        # Connect to the Pico via serial
        try:
            self.serial_connection = serial.Serial(self.port, self.baudrate, timeout=1)
            print(f"Connected to Pico on {self.port} at {self.baudrate} baud.")
        except serial.SerialException as e:
            print(f"Error connecting to Pico: {e}")
            self.serial_connection = None

    def update_gesture(self, new_gesture):
        """Updates the gesture buffer and sends the most common gesture if it changes.

        Args:
            new_gesture (str): The newly detected gesture.
        """
        # Update the gesture buffer
        self.buffer.append(new_gesture)

        # Find the most common gesture in the buffer
        try:
            most_common_gesture = mode(self.buffer)
        except StatisticsError:
            # If mode cannot be determined, continue without change
            most_common_gesture = None

        # If the most common gesture changes, update current_gesture and send the new message
        if most_common_gesture and most_common_gesture != self.current_gesture:
            self.current_gesture = most_common_gesture
            self.send_message(self.current_gesture)

    def send_message(self, message):
        """Sends a message to the Pico over serial.

        Args:
            message (str): The message to send.
        """
        if self.serial_connection and self.serial_connection.is_open:
            try:
                formatted_message = f"{message};"  # Add terminator character to the message
                self.serial_connection.write(formatted_message.encode())
                print(f"Sent message to Pico: {formatted_message}")
            except serial.SerialException as e:
                print(f"Error sending message: {e}")
        else:
            print("Serial connection not available or not open.")

    def close_connection(self):
        """Closes the serial connection to the Pico."""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            print("Closed connection to Pico.")
            
            
class TCPClient:
    """ Class for managing TCP connections to the Intan system."""
    def __init__(self, name, host, port, buffer=1024):
        self.name = name
        self.host = host
        self.port = port
        self.buffer = buffer
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.settimeout(5)  # Timeout after 5 seconds if no data received

    def connect(self):
        self.s.setblocking(True)
        self.s.connect((self.host, self.port))
        self.s.setblocking(False)

    def send(self, data, wait_for_response=False):
        # convert data to bytes if it is not already
        if not isinstance(data, bytes):
            data = data.encode()
        self.s.sendall(data)
        time.sleep(0.01)

        if wait_for_response:
            return self.read()

    def read(self):
        return self.s.recv(self.buffer)

    def close(self):
        self.s.close()

class RingBuffer:
    """Fixed-size ring buffer for storing recent data up to max number of samples. """
    def __init__(self, num_channels, size_max=4000):
        self.max = size_max
        self.samples = np.zeros((size_max, num_channels), dtype=np.float32)
        self.timestamp = np.zeros(size_max, dtype=np.float32)
        self.cur = 0
        self.size = 0

    def append(self, t, x):
        """Adds a new sample to the buffer, removing the oldest sample if full."""
        self.samples[self.cur] = x
        self.timestamp[self.cur] = t
        self.cur = (self.cur + 1) % self.max
        self.size = min(self.size + 1, self.max)

    def get_samples(self, n=1):
        """ Returns the current data in the ring buffer. """
        #return self.samples
        if n > self.size:
            raise ValueError("Requested more samples than available in the buffer.")
        end_idx = self.cur if self.size == self.max else self.size
        start_idx = (end_idx - n) % self.max
        if start_idx < end_idx:
            return self.samples[start_idx:end_idx], self.timestamp[start_idx:end_idx]
        else:
            # When the wrap-around occurs
            return np.vstack((self.samples[start_idx:], self.samples[:end_idx])), \
                np.hstack((self.timestamp[start_idx:], self.timestamp[:end_idx]))

    def is_full(self):
        return self.size == self.max