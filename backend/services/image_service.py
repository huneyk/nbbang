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


# 영수증 quad 유효성 기준 (이미지 크기 대비)
# - 너무 작으면 내부 디테일(로고 등), 너무 크면 이미지 프레임 자체를 잡은 것
QUAD_MIN_AREA_FRAC = 0.15
QUAD_MAX_AREA_FRAC = 0.92
# 바운딩 박스가 이 비율 이상이면 "이미지 프레임" 오감지로 간주
QUAD_MAX_BBOX_FRAC = 0.92


def _is_quad_valid(quad: 'np.ndarray', img_w: int, img_h: int) -> bool:
    """탐지된 quad가 이미지 프레임 자체를 잡은 false positive인지 검증."""
    pts = quad.reshape(-1, 2).astype(np.float32)
    if pts.shape[0] != 4:
        return False

    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    bbox_w = max(1.0, x_max - x_min)
    bbox_h = max(1.0, y_max - y_min)
    img_area = float(img_w * img_h)
    bbox_area = bbox_w * bbox_h

    # 1) 바운딩박스가 이미지 거의 전체면 reject
    if bbox_area >= QUAD_MAX_BBOX_FRAC * img_area:
        return False

    # 2) 사각형 면적(contourArea) 기준도 범위 내
    quad_area = cv2.contourArea(pts)
    if quad_area < QUAD_MIN_AREA_FRAC * img_area:
        return False
    if quad_area > QUAD_MAX_AREA_FRAC * img_area:
        return False

    # 3) 각 변이 이미지 테두리에 붙어있는지 검사 - 3면 이상 붙으면 reject
    margin = max(3, int(min(img_w, img_h) * 0.015))
    hugs = sum([
        x_min < margin,
        y_min < margin,
        x_max > img_w - margin,
        y_max > img_h - margin,
    ])
    if hugs >= 3:
        return False

    # 4) 최소 가로/세로 길이 검증 (너무 납작한 것 제외)
    if bbox_w < img_w * 0.25 or bbox_h < img_h * 0.25:
        return False

    return True


def _find_valid_quads(binary_img: 'np.ndarray', img_w: int, img_h: int) -> list:
    """binary 이미지에서 유효한 영수증 quad 후보들을 모두 수집한다."""
    contours, _ = cv2.findContours(binary_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:15]

    min_area = img_w * img_h * QUAD_MIN_AREA_FRAC
    max_area = img_w * img_h * QUAD_MAX_AREA_FRAC
    valid = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue

        peri = cv2.arcLength(contour, True)
        quad = None
        for eps_mult in (0.02, 0.03, 0.04, 0.06, 0.08):
            approx = cv2.approxPolyDP(contour, eps_mult * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quad = approx
                break

        if quad is None:
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box_area = cv2.contourArea(np.int32(box))
            if min_area <= box_area <= max_area:
                quad = np.int32(box).reshape(4, 1, 2)

        if quad is not None and _is_quad_valid(quad, img_w, img_h):
            valid.append(quad)

    return valid


def _score_quad(quad: 'np.ndarray', img_w: int, img_h: int) -> float:
    """큰 면적 + 직사각형에 가까운 quad를 선호."""
    pts = quad.reshape(-1, 2).astype(np.float32)
    quad_area = cv2.contourArea(pts)
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    bbox_area = max(1.0, (x_max - x_min) * (y_max - y_min))
    rectangularity = quad_area / bbox_area  # 1에 가까울수록 직사각형
    area_frac = quad_area / float(img_w * img_h)
    return rectangularity * area_frac


def crop_receipt(input_path: str, output_path: str = None) -> bool:
    """
    이미지에서 영수증 영역을 감지하고 4점 투시 변환으로 crop합니다.

    여러 전처리 전략(Canny, adaptive threshold, OTSU, HSV white-mask)을 모두 돌려
    후보 quad를 수집한 뒤, 이미지 프레임 오감지를 걸러내고 가장 좋은 후보를 선택합니다.

    Returns True if a valid receipt contour was detected and cropped,
    False if the original image was used (no reliable contour).
    어느 경우든 output_path에는 유효한 JPEG 이미지를 저장합니다.
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
    orig_h, orig_w = img.shape[:2]

    # 더 큰 process_size로 edge 정밀도 향상
    process_size = 1000
    scale = process_size / max(orig_h, orig_w)
    if scale < 1.0:
        resized = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    else:
        resized = img.copy()
        scale = 1.0
    rh, rw = resized.shape[:2]

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    candidates = []  # (source_label, quad)

    # Strategy 1: Canny edge detection (여러 전처리 × 여러 threshold)
    preprocessed = (
        ("canny+gauss", cv2.GaussianBlur(gray, (5, 5), 0)),
        ("canny+bilat", cv2.bilateralFilter(gray, 11, 17, 17)),
    )
    for label, prep in preprocessed:
        for low_t, high_t in ((30, 200), (50, 150), (75, 200), (20, 100)):
            edged = cv2.Canny(prep, low_t, high_t)
            edged = cv2.dilate(edged, dilate_kernel, iterations=2)
            edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, close_kernel, iterations=2)
            for quad in _find_valid_quads(edged, rw, rh):
                candidates.append((f"{label}({low_t},{high_t})", quad))

    # Strategy 2: Adaptive thresholding (두 polarity 모두 시도)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    for block_size in (11, 21, 31, 51):
        adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, block_size, 2,
        )
        for polarity, bin_img in (("adaptive", cv2.bitwise_not(adaptive)), ("adaptive-inv", adaptive)):
            closed = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, close_kernel, iterations=3)
            for quad in _find_valid_quads(closed, rw, rh):
                candidates.append((f"{polarity}(block={block_size})", quad))

    # Strategy 3: OTSU thresholding (두 polarity 모두 시도)
    _, otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    for polarity, bin_img in (("otsu", cv2.bitwise_not(otsu)), ("otsu-inv", otsu)):
        closed = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, close_kernel, iterations=3)
        for quad in _find_valid_quads(closed, rw, rh):
            candidates.append((polarity, quad))

    # Strategy 4: HSV 기반 "밝고 채도 낮은 영역" 탐지 (영수증 용지 = near-white)
    # 어두운 배경(나무/옷감/손가락)에서 흰 영수증을 안정적으로 분리한다.
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    for s_max, v_min in ((60, 140), (80, 120), (100, 100)):
        paper_mask = cv2.inRange(hsv, (0, 0, v_min), (180, s_max, 255))
        paper_mask = cv2.morphologyEx(
            paper_mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)), iterations=3,
        )
        paper_mask = cv2.morphologyEx(
            paper_mask, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=1,
        )
        for quad in _find_valid_quads(paper_mask, rw, rh):
            candidates.append((f"hsv(s<={s_max},v>={v_min})", quad))

    if candidates:
        best_label, best_quad = max(
            candidates, key=lambda lq: _score_quad(lq[1], rw, rh),
        )
        pts = (best_quad.reshape(4, 2) / scale).astype(np.float32)
        cropped = _four_point_transform(orig, pts)

        if cropped.shape[0] > 50 and cropped.shape[1] > 50:
            cv2.imwrite(output_path, cropped, [cv2.IMWRITE_JPEG_QUALITY, 95])
            logger.info(
                f"영수증 crop 완료 ({best_label}, {len(candidates)}개 후보): "
                f"{orig_w}x{orig_h} -> {cropped.shape[1]}x{cropped.shape[0]}"
            )
            return True

    cv2.imwrite(output_path, orig, [cv2.IMWRITE_JPEG_QUALITY, 95])
    logger.info(f"영수증 윤곽 감지 실패 (후보 {len(candidates)}개), 원본 이미지 사용")
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
