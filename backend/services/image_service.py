"""
이미지 처리 서비스
- 이미지 리사이즈 및 최적화
"""

import io
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# 최대 이미지 크기 설정 (OCR 정확도를 위해 충분히 크게 유지)
MAX_IMAGE_DIMENSION = 4000  # 최대 너비/높이 (픽셀) - 고해상도 유지
MAX_FILE_SIZE_KB = 4096  # 최대 파일 크기 (4MB) - API 한도 내에서 충분히
JPEG_QUALITY = 95  # JPEG 압축 품질 (1-100) - 고품질 유지


def resize_image(input_path: str, output_path: str = None) -> str:
    """
    이미지를 리사이즈하고 최적화합니다.
    
    Args:
        input_path: 원본 이미지 경로
        output_path: 저장할 경로 (None이면 원본 덮어쓰기)
        
    Returns:
        저장된 이미지 경로
    """
    if output_path is None:
        output_path = input_path
    
    try:
        with Image.open(input_path) as img:
            original_size = img.size
            original_format = img.format or 'JPEG'
            
            logger.info(f"원본 이미지: {original_size[0]}x{original_size[1]}, 형식: {original_format}")
            
            # EXIF 방향 정보에 따라 이미지 회전
            img = fix_image_orientation(img)
            
            # RGB 모드로 변환 (PNG 투명도 등 처리)
            if img.mode in ('RGBA', 'P'):
                # 투명 배경을 흰색으로 변환
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'RGBA':
                    background.paste(img, mask=img.split()[3])
                else:
                    background.paste(img)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 리사이즈 필요 여부 확인
            width, height = img.size
            if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
                # 비율 유지하면서 리사이즈
                ratio = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"리사이즈: {width}x{height} → {new_width}x{new_height}")
            
            # 품질 조절하면서 저장
            quality = JPEG_QUALITY
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
            
            # 파일 크기 확인 및 추가 압축
            import os
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


def fix_image_orientation(img: Image.Image) -> Image.Image:
    """
    EXIF 방향 정보에 따라 이미지를 올바르게 회전합니다.
    스마트폰으로 촬영한 이미지의 방향 문제를 해결합니다.
    """
    try:
        exif = img._getexif()
        if exif is None:
            return img
        
        orientation_key = 274  # EXIF 방향 태그
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
        
        # 좌우 반전 처리
        if orientation in (2, 4, 5, 7):
            img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        
        return img
        
    except Exception as e:
        logger.warning(f"EXIF 방향 정보 처리 실패: {str(e)}")
        return img


def get_image_info(image_path: str) -> dict:
    """
    이미지 정보를 반환합니다.
    """
    import os
    
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
