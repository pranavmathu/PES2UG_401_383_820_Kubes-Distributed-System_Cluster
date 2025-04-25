import requests
import argparse
from datetime import datetime
import pytz
import time
import threading

NODE_IDS = {
    1: 'Node 1',
    2: 'Node 2',
    3: 'Node 3',
    4: 'Node Minivet'
}

def send_heartbeat(node_id):
    heartbeat_time = datetime.now(pytz.utc).isoformat()
    try:
        response = requests.post('http://localhost:5000/heartbeat', json={
            'node_name': NODE_IDS[node_id],
            'timestamp': heartbeat_time
        })
        if response.status_code == 200:
            print(f'[Node {NODE_IDS[node_id]}] Heartbeat sent at {heartbeat_time}')
        else:
            print(f'[Node {NODE_IDS[node_id]}] Heartbeat failed: {response.status_code} {response.text}')
    except requests.exceptions.RequestException as e:
        print(f'[Node {NODE_IDS[node_id]}] Heartbeat error: {e}')

def register_node(node_id):
    try:
        cpu_cores = 4
        response = requests.post('http://localhost:5000/register', data={
            'node_id': NODE_IDS[node_id],
            'cpu_cores': cpu_cores
        })
        if response.status_code == 200:
            print(f'[Register] Node {NODE_IDS[node_id]} registered.')
        else:
            print(f'[Register] Failed to register node {NODE_IDS[node_id]}: {response.status_code} {response.text}')
    except requests.exceptions.RequestException as e:
        print(f'[Register] Error registering node {NODE_IDS[node_id]}: {e}')

def health_monitor():
    while True:
        print('[Health Monitor] Checking heartbeats...')
        time.sleep(5)

def main():
    parser = argparse.ArgumentParser(description="Node Heartbeat Sender")
    parser.add_argument('--node_id', type=int, required=True)
    args = parser.parse_args()
    node_id = args.node_id

    register_node(node_id)
    while True:
        send_heartbeat(node_id)
        time.sleep(5)

if _name_ == '_main_':
    threading.Thread(target=health_monitor).start()
    main()
