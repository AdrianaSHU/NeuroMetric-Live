import time
import numpy as np
from brainflow.board_shim import BoardShim, BrainFlowInputParams, BoardIds

class EEGSensor:
    """
    Hardware Interface for the OpenBCI Cyton Board (8-Channel EEG).
    Operates entirely on the Edge. BrainFlow connects directly to the local USB dongle, 
    ensuring raw neuro-telemetry is never transmitted over an external network.
    """
    def __init__(self, serial_port='/dev/ttyUSB0'):
        # Target the standard 8-channel Cyton board
        self.board_id = BoardIds.CYTON_BOARD.value
        self.params = BrainFlowInputParams()
        self.params.serial_port = serial_port
        
        self.board = None
        self.is_connected = False
        
        # FIXED: Initialized as an 8-item list to match main.py's expectations
        self.current_signal_sample = [0.0] * 8

    def start(self):
        """
        Initializes the OpenBCI hardware session with Graceful Degradation.
        If the headset is turned off or disconnected, it safely falls back to Camera-Only mode.
        """
        try:
            self.board = BoardShim(self.board_id, self.params)
            self.board.prepare_session()
            self.board.start_stream()
            self.is_connected = True
            print("OpenBCI Cyton Board Ready and Streaming.")
        except Exception as e:
            # Catch the error once and prevent the server loop from crashing
            print(f"OpenBCI Hardware Error: {e}")
            print("Running in CAMERA-ONLY mode. EEG dashboard will show 'OFFLINE'.\n")
            self.is_connected = False
            self.board = None

    def get_raw_data(self, samples=250):
        """
        Fetches the latest block of brainwave data from the hardware buffer safely.
        """
        # 1. If board never connected, return None silently
        if not self.is_connected or self.board is None:
            self.current_signal_sample = [0.0] * 8
            return None
            
        try:
            # 2. Pull data from the C++ BrainFlow ring buffer
            data = self.board.get_current_board_data(samples)
            
            if data is not None and data.shape[1] > 0:
                # 3. Apply DC offset removal across all 8 channels
                # Brainwave hardware inherently has a DC drift (a baseline voltage offset).
                # Subtracting the mean centers the wave at 0.0 for accurate UI rendering.
                # Formula: $x_{centered} = x_{raw} - \mu$
                latest_samples = []
                
                # OpenBCI Cyton EEG channels are located at indices 1 through 8 in the data array
                for i in range(1, 9):
                    raw_val = float(data[i][-1])           # The absolute latest voltage reading
                    avg_val = float(np.mean(data[i]))      # The average voltage of this chunk
                    latest_samples.append(raw_val - avg_val)
                    
                self.current_signal_sample = latest_samples
                return data
                
        except Exception:
            # If the board disconnects mid-stream (e.g., battery dies), silently catch it
            pass
            

            
        # Fallback if no valid data is pulled
        self.current_signal_sample = [0.0] * 8
        return None

    def stop(self):
        """
        Safely shuts down the board to free up the USB port.
        Crucial for preventing 'Port Already in Use' errors on restart.
        """
        if self.board and self.is_connected:
            try:
                self.board.stop_stream()
                self.board.release_session()
                print("OpenBCI Stream Stopped.")
            except Exception:
                pass
        self.is_connected = False