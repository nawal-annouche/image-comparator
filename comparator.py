from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageOps


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


@dataclass(frozen=True)
class LoadedImage:
    name: str
    original_bytes: bytes
    image: Image.Image


def load_image(data: bytes, name: str = "image") -> LoadedImage:
    with Image.open(io.BytesIO(data)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    return LoadedImage(name=name, original_bytes=data, image=image)


def compare_images(left_data: bytes, right_data: bytes, left_name: str = "image A", right_name: str = "image B") -> dict[str, Any]:
    left = load_image(left_data, left_name)
    right = load_image(right_data, right_name)

    exact_file = left.original_bytes == right.original_bytes
    exact_pixels = left.image.size == right.image.size and np.array_equal(np.asarray(left.image), np.asarray(right.image))

    prepared_left = prepare_for_similarity(left.image)
    prepared_right = prepare_for_similarity(right.image)

    phash_left = perceptual_hash(prepared_left)
    phash_right = perceptual_hash(prepared_right)
    ahash_left = average_hash(prepared_left)
    ahash_right = average_hash(prepared_right)
    dhash_left = difference_hash(prepared_left)
    dhash_right = difference_hash(prepared_right)

    phash_distance = hamming_distance(phash_left, phash_right)
    ahash_distance = hamming_distance(ahash_left, ahash_right)
    dhash_distance = hamming_distance(dhash_left, dhash_right)

    phash_similarity = distance_to_similarity(phash_distance, 64)
    ahash_similarity = distance_to_similarity(ahash_distance, 64)
    dhash_similarity = distance_to_similarity(dhash_distance, 64)
    ssim_score = structural_similarity(prepared_left, prepared_right)
    histogram_score = histogram_similarity(prepared_left, prepared_right)

    weighted_score = (
        phash_similarity * 0.42
        + ssim_score * 0.32
        + dhash_similarity * 0.16
        + histogram_score * 0.10
    )

    decision = classify(
        exact_file=exact_file,
        exact_pixels=exact_pixels,
        phash_distance=phash_distance,
        ssim_score=ssim_score,
        weighted_score=weighted_score,
    )

    diff_image = make_diff_image(prepared_left, prepared_right)

    return {
        "decision": decision,
        "score_percent": round(weighted_score * 100, 2),
        "exact_file": exact_file,
        "exact_pixels": exact_pixels,
        "metrics": {
            "phash_distance": phash_distance,
            "phash_similarity_percent": round(phash_similarity * 100, 2),
            "ahash_distance": ahash_distance,
            "ahash_similarity_percent": round(ahash_similarity * 100, 2),
            "dhash_distance": dhash_distance,
            "dhash_similarity_percent": round(dhash_similarity * 100, 2),
            "ssim_percent": round(ssim_score * 100, 2),
            "histogram_percent": round(histogram_score * 100, 2),
        },
        "left": image_info(left),
        "right": image_info(right),
        "diff_image": diff_image,
    }


def prepare_for_similarity(image: Image.Image, size: int = 384) -> Image.Image:
    canvas = Image.new("RGB", (size, size), (245, 245, 245))
    fitted = ImageOps.contain(image.convert("RGB"), (size, size), Image.Resampling.LANCZOS)
    x = (size - fitted.width) // 2
    y = (size - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def image_info(loaded: LoadedImage) -> dict[str, Any]:
    return {
        "name": loaded.name,
        "width": loaded.image.width,
        "height": loaded.image.height,
        "mode": loaded.image.mode,
        "bytes": len(loaded.original_bytes),
    }


def average_hash(image: Image.Image, hash_size: int = 8) -> np.ndarray:
    gray = image.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float32)
    return pixels > pixels.mean()


def difference_hash(image: Image.Image, hash_size: int = 8) -> np.ndarray:
    gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float32)
    return pixels[:, 1:] > pixels[:, :-1]


def perceptual_hash(image: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> np.ndarray:
    img_size = hash_size * highfreq_factor
    gray = image.convert("L").resize((img_size, img_size), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray, dtype=np.float64)
    dct = dct_2d(pixels)
    low_freq = dct[:hash_size, :hash_size]
    median = np.median(low_freq[1:, 1:])
    return low_freq > median


def dct_2d(values: np.ndarray) -> np.ndarray:
    n = values.shape[0]
    transform = dct_matrix(n)
    return transform @ values @ transform.T


def dct_matrix(n: int) -> np.ndarray:
    matrix = np.zeros((n, n), dtype=np.float64)
    factor = np.pi / (2 * n)
    for k in range(n):
        alpha = np.sqrt(1 / n) if k == 0 else np.sqrt(2 / n)
        for i in range(n):
            matrix[k, i] = alpha * np.cos((2 * i + 1) * k * factor)
    return matrix


def hamming_distance(left: np.ndarray, right: np.ndarray) -> int:
    return int(np.count_nonzero(left.flatten() != right.flatten()))


def distance_to_similarity(distance: int, maximum: int) -> float:
    return max(0.0, min(1.0, 1.0 - distance / maximum))


def structural_similarity(left: Image.Image, right: Image.Image) -> float:
    left_gray = np.asarray(left.convert("L"), dtype=np.float64)
    right_gray = np.asarray(right.convert("L"), dtype=np.float64)

    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    mu_x = left_gray.mean()
    mu_y = right_gray.mean()
    sigma_x = left_gray.var()
    sigma_y = right_gray.var()
    covariance = ((left_gray - mu_x) * (right_gray - mu_y)).mean()

    numerator = (2 * mu_x * mu_y + c1) * (2 * covariance + c2)
    denominator = (mu_x**2 + mu_y**2 + c1) * (sigma_x + sigma_y + c2)
    if denominator == 0:
        return 1.0 if np.array_equal(left_gray, right_gray) else 0.0

    return max(0.0, min(1.0, float(numerator / denominator)))


def histogram_similarity(left: Image.Image, right: Image.Image) -> float:
    left_hist = np.asarray(left.histogram(), dtype=np.float64)
    right_hist = np.asarray(right.histogram(), dtype=np.float64)
    left_hist /= max(1.0, left_hist.sum())
    right_hist /= max(1.0, right_hist.sum())
    intersection = np.minimum(left_hist, right_hist).sum()
    return max(0.0, min(1.0, float(intersection)))


def classify(
    *,
    exact_file: bool,
    exact_pixels: bool,
    phash_distance: int,
    ssim_score: float,
    weighted_score: float,
) -> str:
    if exact_file or exact_pixels:
        return "identiques"
    if phash_distance <= 5 and ssim_score >= 0.94:
        return "similaires"
    if weighted_score >= 0.78 and phash_distance <= 14:
        return "similaires"
    return "differentes"


def make_diff_image(left: Image.Image, right: Image.Image) -> str:
    diff = ImageChops.difference(left, right).convert("L")
    diff = ImageEnhance.Contrast(diff).enhance(3.5)
    diff_array = np.asarray(diff, dtype=np.uint8)
    mask = diff_array > 18

    base = Image.blend(left, right, 0.5).convert("RGBA")
    overlay = Image.new("RGBA", left.size, (226, 74, 74, 0))
    alpha = np.zeros(diff_array.shape, dtype=np.uint8)
    alpha[mask] = np.clip(diff_array[mask] * 2, 90, 210)
    overlay.putalpha(Image.fromarray(alpha, mode="L"))
    composed = Image.alpha_composite(base, overlay)

    buffer = io.BytesIO()
    composed.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def find_duplicates(folder: str | Path, threshold: int = 8) -> list[dict[str, Any]]:
    paths = sorted(
        path
        for path in Path(folder).rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    hashes: list[tuple[Path, np.ndarray]] = []
    for path in paths:
        with path.open("rb") as handle:
            loaded = load_image(handle.read(), path.name)
        hashes.append((path, perceptual_hash(prepare_for_similarity(loaded.image))))

    matches: list[dict[str, Any]] = []
    for index, (left_path, left_hash) in enumerate(hashes):
        for right_path, right_hash in hashes[index + 1 :]:
            distance = hamming_distance(left_hash, right_hash)
            if distance <= threshold:
                matches.append(
                    {
                        "left": str(left_path),
                        "right": str(right_path),
                        "phash_distance": distance,
                        "similarity_percent": round(distance_to_similarity(distance, 64) * 100, 2),
                    }
                )
    return matches
