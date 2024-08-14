from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit, join_room
import os
import subprocess
import sys
import math

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Store the container and boxes data in memory
data = {
    "containers": [],
    "generations": []
}

@app.route('/')
def index():
    return send_from_directory(app.root_path, 'index.html')

# Serve the truck files from templates/truck
@app.route('/truck/<path:filename>')
def truck_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'packing-algo', 'templates', 'truck'), filename)


@socketio.on('connect')
def handle_connect():
    join_room('main_room')  # Join the default room
    emit('update_data', data, room='main_room')

def fits(container, box, x, y, z):
    if x + box['width'] > container['width'] or y + box['height'] > container['height'] or z + box['length'] > container['length']:
        return False
    for existing_box in container['boxes']:
        if not (
            x + box['width'] <= existing_box['x'] or x >= existing_box['x'] + existing_box['width'] or
            y + box['height'] <= existing_box['y'] or y >= existing_box['y'] + existing_box['height'] or
            z + box['length'] <= existing_box['z'] or z >= existing_box['z'] + existing_box['length']
        ):
            return False
    return True

def add_box_to_container(container, box):
    orientations = [
        (box['width'], box['height'], box['length']),
        (box['width'], box['length'], box['height']),
        (box['height'], box['width'], box['length']),
        (box['height'], box['length'], box['width']),
        (box['length'], box['width'], box['height']),
        (box['length'], box['height'], box['width']),
    ]
    for width, height, length in orientations:
        box_dimensions = {'width': width, 'height': height, 'length': length}
        for x in range(container['width']):
            for y in range(container['height']):
                for z in range(container['length']):
                    if fits(container, box_dimensions, x, y, z):
                        box['x'] = x
                        box['y'] = y
                        box['z'] = z
                        box['width'] = width
                        box['height'] = height
                        box['length'] = length
                        container['boxes'].append(box)
                        return True
    return False

def organize_boxes_into_layers(container):
    if not container['boxes']:
        return []
    
    total_height = sum(box['height'] for box in container['boxes'])
    average_height = total_height / len(container['boxes'])
    
    layers = {}
    for box in container['boxes']:
        layer = math.floor(box['y'] / average_height)
        if layer not in layers:
            layers[layer] = []
        layers[layer].append(box)
    
    return [layers[key] for key in sorted(layers.keys())]

@socketio.on('add_box')
def handle_add_box(box_data):
    if "containers" in box_data:
        data["containers"] = box_data["containers"]
    for container in data['containers']:
        if add_box_to_container(container, box_data):
            break
    emit('update_data', data, room='main_room', broadcast=True)

@socketio.on('update_generation')
def handle_update_generation(generation_data):
    for container in generation_data['containers']:
        container['layers'] = organize_boxes_into_layers(container)
        del container['boxes']
    data["generations"] = [generation_data]
    emit('update_data', data, room='main_room', broadcast=True)

@socketio.on('remaining_volume')
def handle_remaining_volume(volume_data):
    for container in data["containers"]:
        if container["id"] == volume_data["container_id"]:
            container["total_remaining_volume"] = volume_data["total_remaining_volume"]
            break
    emit('update_data', data, room='main_room', broadcast=True)

@socketio.on('run_packing_algorithm')
def handle_run_packing_algorithm(data):
    print("Received 'run_packing_algorithm' event")
    
    global current_width, current_height, current_length
    
    current_width = data.get('width', current_width)
    current_height = data.get('height', current_height)
    current_length = data.get('length', current_length)
    
    print(f"Running packing algorithm with dimensions: {current_width}x{current_height}x{current_length}")
    
    emit('algorithm_started', {'status': 'Algorithm started running'}, broadcast=True)
    
    python_executable = sys.executable
    script_path = os.path.join(app.root_path, 'packing-algo', 'packing.py')

    try:
        print(f"Executing command: {[python_executable, script_path, str(current_width), str(current_height), str(current_length)]}")
        result = subprocess.run(
            [python_executable, script_path, str(current_width), str(current_height), str(current_length)], 
            check=True, 
            capture_output=True, 
            text=True
        )
        print("Packing algorithm output:", result.stdout)
        if result.stderr:
            print("Packing algorithm error:", result.stderr)
        # Send output to the front end
        emit('packing_algorithm_result', {'output': result.stdout, 'error': result.stderr})
    except subprocess.CalledProcessError as e:
        print("Error running packing.py:", e.stderr)
        emit('packing_algorithm_result', {'output': '', 'error': e.stderr})
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        emit('packing_algorithm_result', {'output': '', 'error': str(e)})


@socketio.on('test_subprocess')
def handle_test_subprocess():
    print("Testing subprocess execution")
    
    try:
        result = subprocess.run(
            ['ls'],  # or 'dir' on Windows
            check=True, 
            capture_output=True, 
            text=True
        )
        print("Subprocess output:", result.stdout)
        if result.stderr:
            print("Subprocess error:", result.stderr)

        # Send the output back to the client
        emit('test_subprocess_result', {'output': result.stdout, 'error': result.stderr})
    except subprocess.CalledProcessError as e:
        print("Error running test subprocess:", e.stderr)
        emit('test_subprocess_result', {'output': '', 'error': e.stderr})
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        emit('test_subprocess_result', {'output': '', 'error': str(e)})

from flask import jsonify
import subprocess
import sys

@app.route('/run_packing_algorithm_test')
def run_packing_algorithm_test():
    try:
        # Directly call the packing.py script with subprocess
        python_executable = sys.executable
        script_path = os.path.join(app.root_path, 'packing-algo', 'packing.py')
        result = subprocess.run(
            [python_executable, script_path, "1200", "1380", "2800"],
            check=True,
            capture_output=True,
            text=True
        )
        return jsonify({"status": "success", "output": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "error": e.stderr})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


current_width = 1200
current_height = 1380
current_length = 2800

@socketio.on('update_container_dimensions')
def handle_update_container_dimensions(data):
    global current_width, current_height, current_length
    current_width = data['width']
    current_height = data['height']
    current_length = data['length']
    print(f"Updated container dimensions received: {current_width}x{current_height}x{current_length}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)



