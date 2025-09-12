import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

def process_image(image, client_name):
    model_path = f"/root/cozmoz_application/from_colab/{client_name}.pt"
    model = YOLO(model_path)

    results = model.predict(source=image, device='cpu')

    top_prediction = results[0].probs.top1
    confidence = round(results[0].probs.top1conf.item(), 1)
    predicted_label = results[0].names[top_prediction]

    if confidence > 0.5:
        res = predicted_label
    else:
        res = "Not certain"
    logger.info(res)

    return res
