"""Optional handwritten text recognition using Microsoft's TrOCR model."""

from typing import List

import cv2
import numpy as np

from .base import OCRProvider, OCRSpan


class TrOCRHandwritingProvider(OCRProvider):
    name = "trocr_handwritten"

    def __init__(self):
        try:
            import torch
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        except ImportError as exc:
            raise RuntimeError(
                "Handwriting OCR dependencies missing. Install "
                "backend/requirements-handwriting.txt"
            ) from exc

        self.torch = torch
        self.processor = TrOCRProcessor.from_pretrained(
            "microsoft/trocr-base-handwritten"
        )
        self.model = VisionEncoderDecoderModel.from_pretrained(
            "microsoft/trocr-base-handwritten"
        )
        self.model.eval()

    @staticmethod
    def _line_boxes(image):
        """Find approximate handwritten text-line regions."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )[1]

        projection = np.count_nonzero(binary, axis=1)
        active = np.where(projection > 0)[0]

        if not len(active):
            return []

        groups = [[int(active[0])]]
        gap_limit = max(5, image.shape[0] // 250)

        for value in active[1:]:
            value = int(value)
            if value - groups[-1][-1] <= gap_limit:
                groups[-1].append(value)
            else:
                groups.append([value])

        boxes = []
        height, width = gray.shape

        for group in groups:
            y1, y2 = max(0, group[0] - 8), min(height, group[-1] + 9)
            crop = binary[y1:y2, :]
            xs = np.where(np.count_nonzero(crop, axis=0) > 0)[0]

            if len(xs) < 3 or y2 - y1 < 8:
                continue

            x1 = max(0, int(xs[0]) - 8)
            x2 = min(width, int(xs[-1]) + 9)

            if x2 - x1 >= 20:
                boxes.append((x1, y1, x2, y2))

        return boxes

    def extract(self, file_path: str, scenario_tag: str | None = None) -> List[OCRSpan]:
        image = cv2.imread(file_path)
        if image is None:
            raise RuntimeError("Unable to open image for handwriting OCR.")

        spans: List[OCRSpan] = []

        for x1, y1, x2, y2 in self._line_boxes(image):
            crop = image[y1:y2, x1:x2]
            crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            pixel_values = self.processor(
                images=crop, return_tensors="pt"
            ).pixel_values

            with self.torch.no_grad():
                output = self.model.generate(
                    pixel_values,
                    max_new_tokens=128,
                    output_scores=True,
                    return_dict_in_generate=True,
                )

            text = self.processor.batch_decode(
                output.sequences, skip_special_tokens=True
            )[0].strip()

            scores = output.scores or ()
            if scores:
                confidence = float(
                    self.torch.stack([
                        self.torch.softmax(step, dim=-1).max(dim=-1).values.mean()
                        for step in scores
                    ]).mean().item()
                )
            else:
                confidence = 0.0

            spans.append({
                "text": text,
                "confidence": confidence,
                "page": 1,
                "bbox": [float(x1), float(y1), float(x2), float(y2)],
                "review_required": confidence < 0.80,
                "recognition_engine": self.name,
            })

        return spans
