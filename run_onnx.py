import onnxruntime as ort
import numpy as np
import cv2
import requests
from io import BytesIO
from PIL import Image

# Load ONNX model
session = ort.InferenceSession("nsfw_model.onnx")

def preprocess_image(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # try multiple approaches to load the image
        try:
            #Direct PIL loading
            img = Image.open(BytesIO(response.content)).convert("RGB")
        except Exception as e:
            print(f"PIL failed: {e}, trying OpenCV")
            # OpenCV fallback
            img_array = np.frombuffer(response.content, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(img)
        
        img = img.resize((224, 224))
        img = np.asarray(img, dtype=np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # [C, H, W]
        img = np.expand_dims(img, axis=0)
        return img
        
    except Exception as e:
        print(f"Image preprocessing error: {e}")
        raise

def softmax(x):
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=1, keepdims=True)

def analyze_image(url: str) -> float:
    try:
        img = preprocess_image(url)
        
        # get the expected input name from the model
        input_name = session.get_inputs()[0].name
        
        # use the correct input name
        output = session.run(None, {input_name: img})[0]
        probs = softmax(output)

        # the nsfw detector categories are in this order:
        # drawings, hentai, neutral, porn, sexy
        hentai = probs[0][1]
        porn = probs[0][3]
        sexy = probs[0][4]

        nsfw_score = float(hentai + porn + sexy)
        return round(nsfw_score, 3)
        
    except Exception as e:
        print(f"ONNX analysis error: {e}")
        return -1.0
