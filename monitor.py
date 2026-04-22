import time
import csv
import psutil

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return float(f.read()) / 1000.0
    except FileNotFoundError:
        return 0.0

def is_main_py_running():
    """Checks if the FastAPI application at app/main.py is currently active."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and 'python' in proc.info['name']:
                if 'app.main' in cmdline or 'app/main.py' in cmdline:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def start_logging():
    filename = "hardware_telemetry.csv"
    
    with open(filename, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["CPU_Temp_C", "CPU_Load_Total_%", "Main_Py_Status"])

    print(f"Monitoring app/main.py... Logging to {filename}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            temp = get_cpu_temp()
            cpu_load = psutil.cpu_percent(interval=1)
            status = "Active" if is_main_py_running() else "Inactive"
            
            with open(filename, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([f"{temp:.1f}°C", f"{cpu_load:.1f}%", status])
            
            print(f"Temp: {temp:.1f}°C | CPU: {cpu_load:.1f}% | app/main.py: {status}")
            
            time.sleep(1) 
            
    except KeyboardInterrupt:
        print("\nLogging stopped.")

if __name__ == "__main__":
    start_logging()