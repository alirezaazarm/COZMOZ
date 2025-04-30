import logging
from ultralytics import YOLO

logger = logging.getLogger(__name__)

def process_image(image):

  model_path= "/root/cozmoz_application/from_colab/best.pt"
  model = YOLO(model_path)

  results = model.predict(source=image, device='cpu')

  top_prediction = results[0].probs.top1
  confidence = results[0].probs.top1conf.item()
  predicted_label = results[0].names[top_prediction]

  if confidence >  0.5:
    res = f"similarity search result by vision model for the shared content is {predicted_label} with the certainty of {confidence}"
  else:
    res = "Not certain about the content, please try again with a different image."
  logger.info(res)

  return  res
