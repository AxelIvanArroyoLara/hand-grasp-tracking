"""Corrección fotométrica y realce opcionales sobre el canal de luminancia."""

import cv2
import numpy as np


class Preprocessor:
    """Aplica transformaciones de luminancia con compuerta de baja iluminación."""

    def __init__(self, options: dict):
        self.illumination = options.get('illumination', 'none')
        self.enhancement = options.get('enhancement', 'none')
        if self.illumination not in {'none', 'gamma', 'clahe', 'equalize'}:
            raise ValueError(f'Corrección de iluminación desconocida: {self.illumination}')
        if self.enhancement not in {'none', 'gaussian', 'bilateral', 'unsharp'}:
            raise ValueError(f'Realce desconocido: {self.enhancement}')
        self.dark_threshold = float(options.get('dark_threshold', 80))
        self.blend = float(options.get('illumination_blend', 0.70))
        self.sharp_gain = float(options.get('sharp_gain', 0.35))
        gamma = float(options.get('gamma', 0.65))
        clip = float(options.get('clahe_clip', 2.0))
        if not (0 <= self.dark_threshold <= 255 and 0 <= self.blend <= 1
                and 0 <= self.sharp_gain <= 1 and 0 < gamma <= 2 and clip > 0):
            raise ValueError('Parámetros de preprocesamiento fuera de rango')
        if self.illumination == 'gamma':
            self.lut = np.round(255 * (np.arange(256) / 255) ** gamma).astype(np.uint8)
        if self.illumination == 'clahe':
            self.clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))

    def apply(self, frame: np.ndarray) -> np.ndarray:
        """Conserva la entrada cuando las técnicas están deshabilitadas o inactivas."""
        correct_light = self.illumination != 'none'
        if correct_light:
            sample = cv2.cvtColor(frame[::8, ::8], cv2.COLOR_BGR2GRAY)
            correct_light = np.median(sample) < self.dark_threshold
        if not correct_light and self.enhancement == 'none':
            return frame
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        luma = ycrcb[:, :, 0].copy()
        if correct_light:
            if self.illumination == 'gamma':
                corrected = cv2.LUT(luma, self.lut)
            elif self.illumination == 'clahe':
                corrected = self.clahe.apply(luma)
            else:
                corrected = cv2.equalizeHist(luma)
            luma = cv2.addWeighted(luma, 1 - self.blend, corrected, self.blend, 0)

        if self.enhancement == 'gaussian':
            luma = cv2.GaussianBlur(luma, (3, 3), 0.7)
        elif self.enhancement == 'bilateral':
            luma = cv2.bilateralFilter(luma, 5, 18, 18)
        elif self.enhancement == 'unsharp':
            blurred = cv2.GaussianBlur(luma, (5, 5), 1)
            luma = cv2.addWeighted(luma, 1 + self.sharp_gain, blurred, -self.sharp_gain, 0)
        ycrcb[:, :, 0] = luma
        return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
