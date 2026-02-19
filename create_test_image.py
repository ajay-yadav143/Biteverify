from PIL import Image, ImageDraw

# Create a simple test image - no randomness, no errors!
img = Image.new('RGB', (500, 400), color=(210, 180, 140))
draw = ImageDraw.Draw(img)

# Draw simple food-like shapes
draw.ellipse([50, 50, 200, 200], fill=(180, 80, 50))    # Red circle (tomato)
draw.ellipse([220, 80, 350, 180], fill=(240, 200, 50))  # Yellow circle (egg)
draw.rectangle([50, 250, 450, 380], fill=(160, 100, 40)) # Brown rectangle (bread)
draw.ellipse([150, 150, 320, 280], fill=(100, 160, 60)) # Green circle (vegetable)
draw.ellipse([300, 200, 420, 320], fill=(200, 60, 60))  # Red circle

img.save('uploads/test_food.jpg')
print('Test image created successfully!')