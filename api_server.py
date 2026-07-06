from flask import Flask, jsonify
import json
import os

app = Flask(__name__)

@app.route('/keys', methods=['GET'])
def get_keys():
    # keys_data.json dosyasını oku
    if os.path.exists('keys_data.json'):
        with open('keys_data.json', 'r') as f:
            try:
                data = json.load(f)
                return jsonify(data)
            except:
                return jsonify([])
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
