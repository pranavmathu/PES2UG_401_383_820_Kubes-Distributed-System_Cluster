from flask import Flask, request, jsonify, render_template_string, redirect
from pymongo import MongoClient
from datetime import datetime
import uuid
import threading
import time

app = Flask(_name_)
client = MongoClient("mongodb://localhost:27017/")
db = client["CC_PROJECT"]
nodes_collection = db["A Distributed Systems Cluster Simulation Framework"]

HEARTBEAT_TIMEOUT = 15  # seconds

@app.route("/register", methods=["POST"])
def register_node():
    node_id = request.form.get("node_id")
    cpu_cores = request.form.get("cpu_cores")
    if not node_id or not cpu_cores:
        return "Missing Node ID or CPU Cores!", 400

    if nodes_collection.find_one({"node_id": node_id}):
        return "Node ID already exists!", 400

    cpu_cores = int(cpu_cores)
    nodes_collection.insert_one({
        "node_id": node_id,
        "cpu_cores": cpu_cores,
        "available_cores": cpu_cores,
        "status": "healthy",
        "pods": [],
        "last_heartbeat": datetime.utcnow()
    })
    print(f"[Register] Node {node_id} registered with {cpu_cores} cores.")
    return redirect("/")

@app.route("/heartbeat", methods=["POST"])
def receive_heartbeat():
    data = request.get_json()
    node_id = data.get("node_name")
    unhealthy_pods = data.get("unhealthy_pods", [])
    heartbeat_time = datetime.utcnow()
    print(f"[API Server] Received heartbeat from {node_id} at {heartbeat_time}")

    result = nodes_collection.find_one({"node_id": node_id})
    if result:
        nodes_collection.update_one(
            {"node_id": node_id},
            {"$set": {"last_heartbeat": heartbeat_time, "status": "healthy"}}
        )
        if unhealthy_pods:
            for pod_id in unhealthy_pods:
                reschedule_pod(pod_id, from_node=node_id)
        return "Heartbeat received", 200
    return "Node not found", 404

@app.route("/launch_pod", methods=["POST"])
def launch_pod():
    cpu_required = int(request.form.get("cpu_cores"))
    policy = request.form.get("scheduling_policy")

    nodes = list(nodes_collection.find({"status": "healthy", "available_cores": {"$gte": cpu_required}}))
    if not nodes:
        return "No suitable nodes found!", 400

    if policy == "best_fit":
        selected_node = min(nodes, key=lambda x: x['available_cores'])
    elif policy == "worst_fit":
        selected_node = max(nodes, key=lambda x: x['available_cores'])
    else:
        return "Invalid scheduling policy!", 400

    pod_id = f"pod_{uuid.uuid4().hex[:6]}"
    new_pod = {
        "pod_id": pod_id,
        "cpu_cores": cpu_required,
        "status": "running",
        "created_at": datetime.utcnow()
    }

    nodes_collection.update_one(
        {"node_id": selected_node["node_id"]},
        {
            "$push": {"pods": new_pod},
            "$inc": {"available_cores": -cpu_required}
        }
    )
    print(f"[Launch] Pod {pod_id} launched on node {selected_node['node_id']}")
    return jsonify({
        "message": "Pod successfully launched!",
        "pod_id": pod_id,
        "assigned_node": selected_node["node_id"]
    })

def reschedule_pod(pod_id, from_node):
    node = nodes_collection.find_one({"node_id": from_node})
    if not node:
        return

    pod = next((p for p in node.get("pods", []) if p["pod_id"] == pod_id), None)
    if not pod:
        return

    cpu_required = pod["cpu_cores"]
    candidates = list(nodes_collection.find({
        "status": "healthy",
        "available_cores": {"$gte": cpu_required},
        "node_id": {"$ne": from_node}
    }))
    if not candidates:
        print(f"[Recovery] No healthy nodes available to reschedule {pod_id}")
        return

    best_fit = min(candidates, key=lambda x: x["available_cores"])
    pod["rescheduled_at"] = datetime.utcnow()

    nodes_collection.update_one(
        {"node_id": best_fit["node_id"]},
        {
            "$push": {"pods": pod},
            "$inc": {"available_cores": -cpu_required}
        }
    )
    nodes_collection.update_one(
        {"node_id": from_node},
        {
            "$pull": {"pods": {"pod_id": pod_id}},
            "$inc": {"available_cores": cpu_required}
        }
    )
    print(f"[Recovery] Pod {pod_id} rescheduled from {from_node} ➜ {best_fit['node_id']}")

def health_monitor():
    while True:
        print("[Health Monitor] Checking heartbeats...")
        now = datetime.utcnow()
        nodes = list(nodes_collection.find({}))
        for node in nodes:
            last_beat = node.get("last_heartbeat", datetime.min)
            time_diff = (now - last_beat).total_seconds()
            if time_diff > HEARTBEAT_TIMEOUT:
                if node["status"] != "unhealthy":
                    print(f"[Health Monitor] ALERT: Node {node['node_id']} marked as UNHEALTHY.")
                    nodes_collection.update_one(
                        {"node_id": node["node_id"]},
                        {"$set": {"status": "unhealthy"}}
                    )
                    for pod in node.get("pods", []):
                        reschedule_pod(pod["pod_id"], from_node=node["node_id"])
            else:
                print(f"[Health Monitor] Node {node['node_id']} is healthy (last heartbeat {int(time_diff)}s ago).")
        time.sleep(5)

@app.route("/nodes", methods=["GET"])
def list_nodes():
    nodes = list(nodes_collection.find({}, {"_id": 0}))
    html = '''
    <html><head><title>Cluster Status</title>
    <meta http-equiv="refresh" content="5">
    </head><body>
    <h2>Real-Time Node and Pod Status</h2>
    <table border="1">
    <tr><th>Node ID</th><th>Status</th><th>CPU Cores</th><th>Available</th><th>Pods</th></tr>
    {% for node in nodes %}
    <tr>
        <td>{{ node.node_id }}</td>
        <td>{{ node.status }}</td>
        <td>{{ node.cpu_cores }}</td>
        <td>{{ node.available_cores }}</td>
        <td>
            {% for pod in node.pods %}
                ID: {{ pod.pod_id }} | CPU: {{ pod.cpu_cores }} 
                {% if pod.rescheduled_at %}(Rescheduled: {{ pod.rescheduled_at }}){% endif %}
                <br>
            {% endfor %}
        </td>
    </tr>
    {% endfor %}
    </table>
    </body></html>
    '''
    return render_template_string(html, nodes=nodes)

@app.route("/", methods=["GET"])
def home():
    return '''
<!DOCTYPE html>
<html>
<head><title>Cluster Simulation</title></head>
<body>
<h2>Register a New Node</h2>
<form action="/register" method="post">
<label for="node_id">Node ID:</label>
<input type="text" name="node_id" required><br>
<label for="cpu_cores">CPU Cores:</label>
<input type="number" name="cpu_cores" required><br>
<button type="submit">Register</button>
</form>

<h2>Launch a Pod</h2>
<form action="/launch_pod" method="post">
<label for="cpu_cores">CPU Cores Required:</label>
<input type="number" name="cpu_cores" required><br>
<label for="scheduling_policy">Scheduling Policy:</label>
<select name="scheduling_policy">
  <option value="best_fit">Best Fit</option>
  <option value="worst_fit">Worst Fit</option>
</select><br>
<button type="submit">Launch Pod</button>
</form>

<h3>View Registered Nodes: <a href="/nodes">Click Here</a></h3>
</body>
</html>
'''

if _name_ == "_main_":
    threading.Thread(target=health_monitor, daemon=True).start()
    app.run(debug=True, port=5000)
