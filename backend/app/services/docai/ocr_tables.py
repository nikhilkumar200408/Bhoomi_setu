"""Conservative grid-based table extraction for scanned document pages."""

from typing import List

import cv2
import numpy as np
import pytesseract
import re
from pytesseract import Output



def _orient_image(image):
    """Correct page orientation and return the applied rotation."""
    try:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        osd = pytesseract.image_to_osd(
            rgb, output_type=Output.STRING, config="--psm 0"
        )
        match = re.search(r"Rotate:\s*(0|90|180|270)", osd)
        rotation = int(match.group(1)) if match else 0

        if rotation == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), 90
        if rotation == 180:
            return cv2.rotate(image, cv2.ROTATE_180), 180
        if rotation == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), 270
    except Exception:
        pass

    return image, 0


def _original_bbox(bbox, width, height, rotation, scale):
    """Map corrected-image coordinates back to original PDF coordinates."""
    x1, y1, x2, y2 = bbox

    if rotation == 90:
        values = [y1, height - x2, y2, height - x1]
    elif rotation == 180:
        values = [width - x2, height - y2, width - x1, height - y1]
    elif rotation == 270:
        values = [width - y2, x1, width - y1, x2]
    else:
        values = [x1, y1, x2, y2]

    return [round(value / scale, 2) for value in values]


def extract_scanned_tables(
    image_path: str,
    page_number: int,
    coordinate_scale: float = 1.0,
) -> tuple[List[dict], str, List[str]]:
    """
    Detect clearly ruled tables and OCR individual cells.

    Returns tables, detection status and warnings.
    Does not guess tables from ordinary text alignment.
    """
    warnings: List[str] = []

    image = cv2.imread(image_path)
    if image is None:
        return [], "FAILED", ["SCANNED_TABLE_IMAGE_UNAVAILABLE"]

    original_height, original_width = image.shape[:2]
    image, rotation = _orient_image(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]

    if height < 100 or width < 100:
        return [], "NO_TABLES", []

    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        10,
    )

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(20, width // 30), 1)
    )
    vertical_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(20, height // 30))
    )

    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, horizontal_kernel
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, vertical_kernel
    )

    grid = cv2.add(horizontal, vertical)
    grid = cv2.dilate(
        grid,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )

    contours, _ = cv2.findContours(
        grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if w < width * 0.15 or h < height * 0.025:
            continue

        if w * h < width * height * 0.002:
            continue

        horizontal_crop = horizontal[y:y + h, x:x + w]
        vertical_crop = vertical[y:y + h, x:x + w]

        row_projection = np.count_nonzero(horizontal_crop, axis=1)
        col_projection = np.count_nonzero(vertical_crop, axis=0)

        row_positions = np.where(row_projection >= max(5, int(w * 0.25)))[0]
        col_positions = np.where(col_projection >= max(5, int(h * 0.25)))[0]

        def merge_positions(values, minimum_gap=5):
            if len(values) == 0:
                return []
            groups = [[int(values[0])]]
            for value in values[1:]:
                value = int(value)
                if value - groups[-1][-1] <= minimum_gap:
                    groups[-1].append(value)
                else:
                    groups.append([value])
            return [int(sum(group) / len(group)) for group in groups]

        rows = merge_positions(row_positions)
        cols = merge_positions(col_positions)

        # Require a real grid: at least two rows and two columns.
        if len(rows) < 3 or len(cols) < 3:
            continue

        candidates.append((x, y, w, h, rows, cols))

    if not candidates:
        return [], "NO_TABLES", []

    tables = []
    candidates.sort(key=lambda item: (item[1], item[0]))

    for table_index, (x, y, w, h, row_lines, col_lines) in enumerate(candidates):
        cell_rows = []
        cell_metadata = []
        low_confidence = False

        for row_index in range(len(row_lines) - 1):
            row_values = []
            row_cells = []

            for col_index in range(len(col_lines) - 1):
                x1 = x + col_lines[col_index] + 2
                x2 = x + col_lines[col_index + 1] - 2
                y1 = y + row_lines[row_index] + 2
                y2 = y + row_lines[row_index + 1] - 2

                if x2 <= x1 or y2 <= y1:
                    row_values.append("")
                    row_cells.append({
                        "text": "",
                        "confidence": 0.0,
                        "review_required": True,
                        "bbox": [],
                    })
                    low_confidence = True
                    continue

                cell_image = gray[y1:y2, x1:x2]

                cell_text = ""
                confidence = 0.0

                try:
                    # Upscale small table cells before OCR.
                    enlarged = cv2.resize(
                        cell_image, None, fx=3, fy=3,
                        interpolation=cv2.INTER_CUBIC
                    )

                    variants = [enlarged]

                    # Try two additional thresholding methods.
                    _, otsu = cv2.threshold(
                        enlarged, 0, 255,
                        cv2.THRESH_BINARY + cv2.THRESH_OTSU
                    )
                    variants.append(otsu)

                    adaptive = cv2.adaptiveThreshold(
                        enlarged, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY, 31, 11
                    )
                    variants.append(adaptive)

                    candidates = []

                    for variant in variants:
                        for psm in (6, 7, 11):
                            data = pytesseract.image_to_data(
                                variant,
                                lang="eng",
                                config=f"--oem 3 --psm {psm}",
                                output_type=pytesseract.Output.DICT,
                            )

                            words = []
                            scores = []

                            for word, raw_conf in zip(
                                data["text"], data["conf"]
                            ):
                                word = str(word).strip()
                                try:
                                    score = float(raw_conf)
                                except (TypeError, ValueError):
                                    continue

                                if word and score >= 0:
                                    words.append(word)
                                    scores.append(score)

                            if words and scores:
                                avg_conf = sum(scores) / len(scores)
                                candidate_text = " ".join(words)
                                # Prefer readable candidates, not empty output.
                                candidate_score = (
                                    avg_conf + min(len(words), 4) * 1.5
                                )
                                candidates.append((
                                    candidate_score,
                                    candidate_text,
                                    avg_conf / 100.0,
                                ))

                    if candidates:
                        _, cell_text, confidence = max(
                            candidates, key=lambda item: item[0]
                        )
                        confidence = round(confidence, 3)

                except Exception:
                    cell_text = ""
                    confidence = 0.0

                review_required = confidence < 0.60 or not cell_text
                low_confidence = low_confidence or review_required

                bbox = _original_bbox(
                    [x1, y1, x2, y2],
                    original_width,
                    original_height,
                    rotation,
                    coordinate_scale,
                )

                row_values.append(cell_text)
                row_cells.append({
                    "text": cell_text,
                    "confidence": confidence,
                    "review_required": review_required,
                    "bbox": bbox,
                })

            cell_rows.append(row_values)
            cell_metadata.append(row_cells)

        if not any(any(cell for cell in row) for row in cell_rows):
            continue

        tables.append({
            "table_index": table_index,
            "page": page_number,
            "bbox": _original_bbox(
                [x, y, x + w, y + h],
                original_width,
                original_height,
                rotation,
                coordinate_scale,
            ),
            "rows": cell_rows,
            "cells": cell_metadata,
            "extraction_method": "OPENCV_GRID_TESSERACT_CELL_OCR",
            "review_required": low_confidence,
        })

    if not tables:
        return [], "NO_TABLES", []

    if any(table["review_required"] for table in tables):
        warnings.append("SCANNED_TABLE_LOW_CONFIDENCE_CELLS")

    return tables, "COMPLETED", warnings
