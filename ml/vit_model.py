from transformers import ViTForImageClassification, ViTImageProcessor
from PIL import Image
import torch

model = ViTForImageClassification.from_pretrained("google/vit-base-patch16-224")
processor = ViTImageProcessor.from_pretrained("google/vit-base-patch16-224")

def classify_image(image_path):
    image = Image.open(image_path)
    inputs = processor(images=image, return_tensors="pt")

    outputs = model(**inputs)
    logits = outputs.logits
    predicted_class = logits.argmax(-1).item()

    return predicted_class
