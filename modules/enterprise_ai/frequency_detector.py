import cv2
import numpy as np

def detect_frequency_anomaly(image_path):
    img = cv2.imread(image_path, 0)
    f = np.fft.fft2(img)
    fshift = np.fft.fftshift(f)
    magnitude = 20 * np.log(np.abs(fshift) + 1)

    mean_mag = np.mean(magnitude)
    std_mag = np.std(magnitude)

    anomaly_score = abs(std_mag - mean_mag) / (mean_mag + 1e-5)

    return round(min(anomaly_score * 100, 100), 2)
