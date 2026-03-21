"""
이미지 처리 서비스
- EXIF 방향 보정
- 영수증 영역 자동 crop
- 이미지 리사이즈 및 최적화
- 저장용 다운사이즈
"""

import io
import os
import shutil
import logging
from PIL import Image

try:
    import cv2
    import numpy as np
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False

logger = logging.getLogger(__name__)

MAX_IMAGE_DIMENSION = 4000
MAX_FILE_SIZE_KB = 4096
JPEG_QUALITY = 95

STORAGE_MAX_DIMENSION = 1500
STORAGE_MAX_FILE_SIZE_KB = 500
STORAGE_JPEG_QUALITY = 85


def fix_image_orientation(img: Image.Image) -> Image.Image:
    """EXIF 방향 정보에 따라 이미지를 올바르게 회전합니다."""
    try:
        exif = img._getexif()
        if exif is None:
            return img

        orientation_key = 274
        if orientation_key not in exif:
            return img

        orientation = exif[orientation_key]

        rotations = {
            3: Image.Transpose.ROTATE_180,
            6: Image.Transpose.ROTATE_270,
            8: Image.Transpose.ROTATE_90,
        }

        if orientation in rotations:
            img = img.transpose(rotations[orientation])
            logger.info(f"이미지 방향 보정: orientation={orientation}")

        if orientation in (2, 4, 5, 7):
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

        return img

    except Exception as e:
        logger.warning(f"EXIF 방향 정보 처리 실패: {str(e)}")
        return img


def _to_rgb_pil(img: Image.Image) -> Image.Image:
    """PIL 이미지를 RGB로 변환합니다."""
    if img.mode in ('RGBA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'RGBA':
            background.paste(img, mask=img.split()[3])
        else:
            background.paste(img)
        return background
    if img.mode != 'RGB':
        return img.convert('RGB')
    return img


def fix_orientation_only(input_path: str, output_path: str = None) -> str:
    """EXIF 방향 보정 + RGB 변환만 수행합니다 (리사이즈 없음)."""
    if output_path is None:
        output_path = input_path

    with Image.open(input_path) as img:
        img = fix_image_orientation(img)
        img = _to_rgb_pil(img)
        img.save(output_path, 'JPEG', quality=95, optimize=True)

    return output_path


# ===== OpenCV 기반 영수증 자동 crop =====

def _order_points(pts: 'np.ndarray') -> 'np.ndarray':
    """4개 점을 top-left, top-right, bottom-right, bottom-left 순서로 정렬합니다."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def _four_point_transform(image: 'np.ndarray', pts: 'np.ndarray') -> 'np.ndarray':
    """4점 원근 변환으로 정면 뷰를 생성합니다."""
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect

    max_width = max(
        int(np.linalg.norm(br - bl)),
        int(np.linalg.norm(tr - tl))
    )
    max_height = max(
        int(np.linalg.norm(tr - br)),
        int(np.linalg.norm(tl - bl))
    )

    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (max_width, max_height))


def crop_receipt(input_path: str, output_path: str = None) -> bool:
    """
    이미지에서 영수증 영역을 감지하고 crop합니다.
    Returns True if receipt contour was detected, False otherwise.
    어느 경우든 output_path에 유효한 이미지를 저장합니다.
    """
    if output_path is None:
        output_path = input_path

    if not HAS_OPENCV:
        logger.warning("OpenCV 미설치, 영수증 자동 crop 건너뜀")
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return False

    img = cv2.imread(input_path)
    if img is None:
        logger.warning(f"이미지 읽기 실패: {input_path}")
        if input_path != output_path:
            shutil.copy2(input_path, output_path)
        return False

    orig = img.copy()
    h, w = img.shape[:2]

    process_size = 500
    scale = process_size / max(h, w)
    if scale < 1.0:
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        resized = img.copy()
        scale = 1.0

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    receipt_contour = None
    for low_thresh, high_thresh in [(30, 200), (50, 150), (75, 200), (20, 100)]:
        edged = cv2.Canny(blurred, low_thresh, high_thresh)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edged = cv2.dilate(edged, kernel, iterations=2)

        contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

        for contour in contours:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            if len(approx) == 4:
                area = cv2.contourArea(approx)
                img_area = resized.shape[0] * resized.shape[1]
                if area > img_area * 0.15:
                    receipt_contour = approx
                    break

        if receipt_contour is not None:
            break

    if receipt_contour is not None:
        pts = (receipt_contour.reshape(4, 2) / scale).astype(np.float32)
        cropped = _four_point_transform(orig, pts)

        if cropped.shape[0] > 50 and cropped.shape[1] > 50:
            cv2.imwrite(output_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            logger.info(f"영수증 crop 완료: {w}x{h} -> {cropped.shape[1]}x{cropped.shape[0]}")
            return True

    cv2.imwrite(output_path, orig, [cv2.IMWRITE_JPEG_QUALITY, 95])
    logger.info("영수증 윤곽 감지 실패, 원본 이미지 사용")
    return False


# ===== 리사이즈 및 다운사이즈 =====

def resize_image(input_path: str, output_path: str = None) -> str:
    """OCR 분석을 위해 이미지를 리사이즈/최적화합니다 (max 4000px, max 4MB)."""
    if output_path is None:
        output_path = input_path

    try:
        with Image.open(input_path) as img:
            original_size = img.size
            original_format = img.format or 'JPEG'

            logger.info(f"원본 이미지: {original_size[0]}x{original_size[1]}, 형식: {original_format}")

            img = fix_image_orientation(img)
            img = _to_rgb_pil(img)

            width, height = img.size
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                ratio = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"리사이즈: {width}x{height} -> {new_width}x{new_height}")

            quality = JPEG_QUALITY
            img.save(output_path, 'JPEG', quality=quality, optimize=True)

            file_size_kb = os.path.getsize(output_path) / 1024
            while file_size_kb > MAX_FILE_SIZE_KB and quality > 30:
                quality -= 10
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
                file_size_kb = os.path.getsize(output_path) / 1024
                logger.info(f"압축 조정: quality={quality}, 크기={file_size_kb:.1f}KB")

            logger.info(f"최종 파일 크기: {file_size_kb:.1f}KB")
            return output_path

    except Exception as e:
        logger.error(f"이미지 리사이즈 오류: {str(e)}")
        raise


def downsize_for_storage(input_path: str, output_path: str = None) -> str:
    """GridFS 저장을 위해 이미지를 다운사이즈합니다 (max 1500px, max 500KB)."""
    if output_path is None:
        output_path = input_path

    try:
        with Image.open(input_path) as img:
            img = _to_rgb_pil(img)

            width, height = img.size
            if width > STORAGE_MAX_DIMENSION or height > STORAGE_MAX_DIMENSION:
                ratio = min(STORAGE_MAX_DIMENSION / width, STORAGE_MAX_DIMENSION / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"저장용 다운사이즈: {width}x{height} -> {new_width}x{new_height}")

            quality = STORAGE_JPEG_QUALITY
            img.save(output_path, 'JPEG', quality=quality, optimize=True)

            file_size_kb = os.path.getsize(output_path) / 1024
            while file_size_kb > STORAGE_MAX_FILE_SIZE_KB and quality > 30:
                quality -= 10
                img.save(output_path, 'JPEG', quality=quality, optimize=True)
                file_size_kb = os.path.getsize(output_path) / 1024

            logger.info(f"저장용 이미지: quality={quality}, 크기={file_size_kb:.1f}KB")
            return output_path

    except Exception as e:
        logger.error(f"이미지 다운사이즈 오류: {str(e)}")
        raise


def get_image_info(image_path: str) -> dict:
    """이미지 정보를 반환합니다."""
    try:
        with Image.open(image_path) as img:
            file_size = os.path.getsize(image_path)
            return {
                'width': img.size[0],
                'height': img.size[1],
                'format': img.format,
                'mode': img.mode,
                'file_size_kb': round(file_size / 1024, 1)
            }
    except Exception as e:
        logger.error(f"이미지 정보 조회 오류: {str(e)}")
        return None
