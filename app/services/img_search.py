import pandas as pd
import torch
import pickle
import torch.nn.functional as F
from transformers import CLIPProcessor, CLIPModel

def load_precomputed_data():
    """Load the precomputed features and metadata"""
    with open("/root/cozmoz_application/drive/inference.pkl", 'rb') as f:
        data_dict = pickle.load(f)
    return data_dict['image_features'], data_dict['image_paths'], data_dict['image_index']

def initialize_model():
    """Initialize CLIP model and processor"""
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()
    return model, processor, device

def search_by_image(image, model, processor, device, image_features, image_paths, image_index, top_k=5):
    """Search for similar images using CLIP"""
    with torch.no_grad():
        inputs = processor(images=image, return_tensors="pt")
        image_features_query = model.get_image_features(inputs['pixel_values'].to(device))
        image_features_query = F.normalize(image_features_query.cpu(), dim=-1)

        similarities = torch.matmul(image_features_query, image_features.t())[0]
        top_indices = torch.topk(similarities, min(top_k, len(image_paths))).indices

        results = []
        for idx in top_indices:
            img_path = image_paths[idx]
            for item in image_index:
                if item['path'] == img_path:
                    results.append({
                        'path': img_path,
                        'similarity': similarities[idx].item(),
                        'metadata': item
                    })
                    break
        return results

def process_image(image):
    try:
        image_features, image_paths, image_index = load_precomputed_data()

        model, processor, device = initialize_model()

        data = pd.read_csv("/root/cozmoz_application/drive/translated_data.csv", encoding='utf-8', engine='python')

        results = search_by_image(
            image,
            model,
            processor,
            device,
            image_features,
            image_paths,
            image_index,
            top_k=1
        )

        output_logs = []
        for i, result in enumerate(results, 1):
            try:
                persian_title = f"similarity search for incoming image with certainty of {result['similarity']:.3f} is: {data.loc[data['product_id'] == int(result['metadata']['pID']), 'title'].values[0]} "
            except:
                persian_title = "   some bugs happend in similarity search"

            output_logs.extend([persian_title])

        return "\n".join(output_logs)
    except Exception as e:
        raise Exception(f"Detailed error: {str(e)}")