import logging
import torch
import pickle
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel
from collections import Counter

logger = logging.getLogger(__name__)


def load_inference():
    """Load the precomputed features and metadata"""
    logger.info("Loading precomputed data from pickle file.")
    try:
        with open("/root/cozmoz_application/from_colab/inference.pkl", 'rb') as f:
            data_dict = pickle.load(f)
        logger.info("Precomputed data loaded successfully.")
        return data_dict['image_features'], data_dict['image_index']
    except Exception as e:
        logger.error(f"Error loading precomputed data: {str(e)}")
        raise

def initialize_model():
    """Initialize CLIP model and processor"""
    logger.info("Initializing CLIP model and processor.")
    try:
        model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        device = torch.device("cpu")
        model = model.to(device)
        model.eval()
        logger.info(f"CLIP model and processor initialized successfully. Using device: {device}.")
        return model, processor, device
    except Exception as e:
        logger.error(f"Error initializing CLIP model: {str(e)}")
        raise

def search_by_image(image, model, processor, device, image_features, image_index, top_k=5):
    """Search for similar images using CLIP"""
    logger.info(f"Searching for similar images with top_k={top_k}.")
    try:
        with torch.no_grad():
            inputs = processor(images=image, return_tensors="pt")
            image_features_query = model.get_image_features(inputs['pixel_values'].to(device))
            image_features_query = F.normalize(image_features_query.cpu(), dim=-1)

            similarities = torch.matmul(image_features_query, image_features.t())[0]
            top_indices = torch.topk(similarities, min(top_k, len(image_index))).indices

            most_probable = Counter(top_indices).most_common(1)[0]
            logger.info(f"Most probable match: {image_index[most_probable[0]]['title']} with {most_probable[1]} repeats in {top_k} top matches.")

            return {'title':image_index[most_probable[0]]['title'], 'repeat_count':most_probable[1]}
    except Exception as e:
        logger.error(f"Error during image search: {str(e)}")
        raise

def process_image(image, top_k=5):
    try:
        image_features, image_index = load_inference()

        model, processor, device = initialize_model()

        diag = search_by_image( image, model, processor, device, image_features, image_index, top_k=top_k )

        if diag['repeat_count'] < top_k/2:
            logger.info("No certain matches found, returning None.")
            return None
        else:
            logger.info(f"Most probable match: {diag['title']} with repeat count {diag['repeat_count']} in {top_k} top matches..")
            return diag['title']

    except Exception as e:
        logger.error(f"Error in image processing pipeline: {str(e)}")
        raise Exception(f"Detailed error: {str(e)}")