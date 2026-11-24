"""Dibujo de landmarks, cuadro y eventos en las imágenes de salida."""

import cv2
import numpy as np

from src.contracts import valid_points

FINGERS = ((0, 1, 2, 3, 4), (0, 5, 6, 7, 8), (5, 9, 10, 11, 12),
           (9, 13, 14, 15, 16), (13, 17, 18, 19, 20), (17, 0))


def overlay(frame, points, index, name, event=None, color=(85, 235, 125)):
    """Dibuja la pose en píxeles originales y muestra la última transición reciente."""
    result = frame.copy()
    if valid_points(points):
        pixels = points.round().astype(np.int32)
        for path in FINGERS:
            cv2.polylines(result, [pixels[list(path)]], False, color, 2, cv2.LINE_AA)
        for xy in pixels:
            cv2.circle(result, tuple(xy), 3, color, -1, cv2.LINE_AA)
    scale = min(0.8, max(0.3, result.shape[1] / 750))
    label = f"{name} | cuadro {index}" + (" | sin mano" if not valid_points(points) else "")
    cv2.rectangle(result, (0, 0), (result.shape[1], 52 if event else 29), (25, 25, 25), -1)
    cv2.putText(result, label, (6, 21), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
    if event:
        cv2.putText(result, f"{event.kind.upper()} @ {event.frame}", (6, 43),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
    return result


def video_writer(path, frame, fps):
    """Abre un codificador MP4 y verifica la disponibilidad del códec."""
    height, width = frame.shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        writer.release()
        raise ValueError(f"No se pudo crear el MP4 {path}")
    return writer
