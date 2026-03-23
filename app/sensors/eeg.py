import time
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

class EEGSensor:
    def __init__(self, serial_port='/dev/ttyUSB0'):
        self.board_id = BoardIds.CYTON_BOARD.value
        self.params = BrainFlowInputParams()
        self.params.serial_port = serial_port
        self.board = None
        self.is_connected = False
        self.current_signal_sample = [0.0] * 8

    def start(self):
        try:
            self.board = BoardShim(self.board_id, self.params)
            self.board.prepare_session()
            self.board.start_stream()
            self.is_connected = True
            print("[Hardware] OpenBCI Cyton Board Ready and Streaming.")
        except Exception as e:
            print(f"[Hardware] EEG Connection Error: {e}")
            self.is_connected = False
            self.board = None

    def get_raw_data(self, samples=250):
        """Fetches the latest block of brainwave data safely."""
        if not self.is_connected or self.board is None:
            self.current_signal_sample = [0.0] * 8
            return None
            
        try:
            data = self.board.get_current_board_data(samples)
            if data is not None and data.shape[1] > 0:
                # Update real-time sample for dashboard (Channels 1-8)
                latest_raw = data[1:9, -1]
                latest_centered = []
                for i in range(8):
                    ch_mean = np.mean(data[i+1])
                    latest_centered.append(float(latest_raw[i] - ch_mean))
                
                self.current_signal_sample = latest_centered
                return data
        except Exception:
            self.is_connected = False
        return None

    def stop(self):
        if self.board and self.is_connected:
            try:
                self.board.stop_stream()
                self.board.release_session()
                print("[Hardware] EEG Stream Stopped.")
            except: pass
        self.is_connected = False