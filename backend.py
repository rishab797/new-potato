from fastapi import FastAPI, File, UploadFile, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np
import tensorflow as tf
import cv2
import base64

# ---- Add this for API key protection ----
API_KEY = "your-secret-api-key"  # 🔐 Replace with your actual key

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")
# -----------------------------------------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production: allow only trusted domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = tf.keras.models.load_model("unet_model.keras")
IMG_SIZE = 256
CLASS_COLORS = {0: (0, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255)}

def decode_mask_to_overlay(image_bgr, mask):
    overlay = image_bgr.copy()
    for class_id, color in CLASS_COLORS.items():
        overlay[mask == class_id] = (
            np.array(overlay[mask == class_id]) * 0.5 + np.array(color) * 0.5
        ).astype(np.uint8)
    return overlay

def image_to_base64(img: np.ndarray) -> str:
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode("utf-8")


@app.post("/predict_severity")
async def predict_severity(
    file: UploadFile = File(...),
    x_api_key: str = Depends(verify_api_key)  # 🔐 Require API key
):
    try:
        contents = await file.read()
        file_bytes = np.frombuffer(contents, np.uint8)
        img_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        img_resized = cv2.resize(img_bgr, (IMG_SIZE, IMG_SIZE))
        img_norm = img_resized.astype(np.float32) / 255.0
        img_input = np.expand_dims(img_norm, axis=0)

        prediction = model.predict(img_input)[0]
        mask = np.argmax(prediction, axis=-1).astype(np.uint8)

        center_pixel = prediction[IMG_SIZE // 2, IMG_SIZE // 2]
        print(f"Center pixel confidence: {center_pixel}")

        unique, counts = np.unique(mask, return_counts=True)
        class_counts = {int(k): int(v) for k, v in zip(unique, counts)}

        healthy = class_counts.get(1, 0)
        diseased = class_counts.get(2, 0)
        severity_percent = (diseased / (healthy + diseased)) * 100 if (healthy + diseased) > 0 else 0.0

        overlay = decode_mask_to_overlay(img_resized, mask)
        mask_base64 = image_to_base64(overlay)

        return {
            "severity": round(severity_percent, 2),
            "class_counts": class_counts,
            "segmentation_mask_base64": mask_base64
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

