import collectd
import socket
import threading
import time

# Define the UDP address and port to listen on
UDP_IP = "0.0.0.0"  # Listen on all available network interfaces
UDP_PORT = 5005     # Choose a port number to listen on

stop_flag = threading.Event()  # Workaround for hanging collectd

# Mapping iridium-extractor output > human readable
custom_names = {
    'i': 'Bursts detected',
    'i_avg': 'Average bursts',
    'q_max': 'Queue size',
    'i_ok': 'Percentage of OK bursts',
    'o': 'Output frames',
    'okr': 'OK frames percentage',
    'okp': 'OK frames',
    'ok_avg': 'Average OK frames',
    'okt': 'Total OK frames',
    'okt_avg': 'Average OK frames',
    'd': 'Dropped bursts',
}

sock = None
buffer = []
last_update_timestamp = 0

def parse_udp_data(data):
    """
    Parse UDP data and extract metrics.
    """
    metrics = {}
    parts = data.decode().strip().split("|")
    for part in parts:
        key_value = part.strip().split(":")
        if len(key_value) == 2:
            key, value = key_value
            # Remove any non-numeric characters except '/' and convert to float
            value = ''.join(c for c in value if c.isdigit() or c in {'/', '.', '-'})
            if value:
                # Ensure the value is not empty after removing non-numeric characters
                metrics[key.strip()] = value
    return metrics

def read_udp_data():
    """
    Read UDP data and store metrics in buffer.
    """
    global sock
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((UDP_IP, UDP_PORT))
        sock.settimeout(1.0)  # Set a timeout of 1 second

    while not stop_flag.is_set():
        try:
            data, addr = sock.recvfrom(1024)
            metrics = parse_udp_data(data)
            buffer.append(metrics)
        except socket.timeout:
            continue  # Timeout reached, loop will check stop_flag and continue

def read_callback():
    """
    Collectd read callback to dispatch metrics.
    """
    global buffer, last_update_timestamp
    if buffer:
        metrics = buffer.pop(0)
        current_timestamp = int(metrics.get('timestamp', time.time()))  # Use timestamp from data or current time
        if last_update_timestamp != current_timestamp:
            for key, value in metrics.items():
                if key != 'timestamp':  # Skip timestamp key
                    val = collectd.Values(plugin="iridium")
                    val.plugin_instance = custom_names.get(key, key)
                    val.type_instance = custom_names.get(key, key)
                    val.values = [float(value)]
                    # Specify the type for each metric
                    if key in {"i", "i_avg", "q_max", "o", "okp", "okt_avg"}:
                        val.type = "gauge"
                    elif key in {"i_ok", "ok_avg", "okr"}:
                        val.type = "percent"
                    elif key in {"okt", "d"}:
                        val.type = "counter"
                    else:
                        # Default type (gauge) for unknown metrics
                        val.type = "gauge"
                    val.dispatch()
            last_update_timestamp = current_timestamp

def init_callback():
    """
    Initialization callback function for Collectd.
    """
    global read_thread
    collectd.info("Initializing UDP data read plugin.")
    read_thread = threading.Thread(target=read_udp_data)
    read_thread.start()

def shutdown_callback():
    """
    Shutdown callback function for Collectd.
    """
    collectd.info("Shutdown signal received, setting stop flag.")
    stop_flag.set()  # Signal the read loop to stop
    if read_thread:
        read_thread.join()  # Wait for the read thread to exit
    collectd.info("Shutdown complete.")

# Register callbacks
collectd.register_init(init_callback)
collectd.register_read(read_callback)
collectd.register_shutdown(shutdown_callback)
