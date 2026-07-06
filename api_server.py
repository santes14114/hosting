from flask import Flask, jsonify
import json
import os

app = Flask(__name__)

# Botun veri dosyasının yolu
DATA_FILE = 'keys_data.json'

@app.route('/keys', methods=['GET'])
def get_keys():
    # Anahtarları JSON olarak dışarıya ver
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                return jsonify(data)
            except:
                return jsonify([])
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
