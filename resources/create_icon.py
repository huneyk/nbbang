#!/usr/bin/env python3
"""
macOS 앱 아이콘 생성 스크립트
icon.jpg 이미지를 macOS 앱 아이콘(.icns)으로 변환합니다.
"""

import os
import subprocess
from pathlib import Path

# 아이콘 크기 목록 (macOS 표준)
ICON_SIZES = [16, 32, 64, 128, 256, 512, 1024]


def create_icon_from_jpg():
    """icon.jpg를 사용하여 icns 아이콘 생성"""
    try:
        from PIL import Image
    except ImportError:
        print("PIL이 설치되어 있지 않습니다. pip install pillow 를 실행해주세요.")
        return False
    
    script_dir = Path(__file__).parent
    source_image = script_dir / "icon.jpg"
    
    if not source_image.exists():
        print(f"원본 이미지를 찾을 수 없습니다: {source_image}")
        return False
    
    iconset_dir = script_dir / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)
    
    # 원본 이미지 로드
    print(f"원본 이미지 로드 중: {source_image}")
    original = Image.open(source_image)
    
    # RGBA로 변환 (투명도 지원)
    if original.mode != 'RGBA':
        original = original.convert('RGBA')
    
    # 정사각형으로 크롭 (중앙 기준)
    width, height = original.size
    min_dim = min(width, height)
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim
    original = original.crop((left, top, right, bottom))
    
    print(f"아이콘셋 생성 중...")
    
    for size in ICON_SIZES:
        # 고품질 리사이즈
        resized = original.resize((size, size), Image.LANCZOS)
        
        # @1x 저장
        resized.save(iconset_dir / f"icon_{size}x{size}.png", "PNG")
        
        # @2x 저장 (512 이하만 - 1024의 @2x는 2048이 되어 너무 큼)
        if size <= 512:
            resized_2x = original.resize((size * 2, size * 2), Image.LANCZOS)
            resized_2x.save(iconset_dir / f"icon_{size}x{size}@2x.png", "PNG")
    
    print(f"아이콘 이미지가 생성되었습니다: {iconset_dir}")
    
    # iconutil로 icns 생성
    icns_path = script_dir / "icon.icns"
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=True
        )
        print(f"✅ 아이콘 파일이 생성되었습니다: {icns_path}")
        
        # iconset 폴더 정리
        import shutil
        shutil.rmtree(iconset_dir)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"iconutil 실행 실패: {e}")
        return False


def create_icon_with_pil():
    """PIL을 사용하여 기본 아이콘 생성 (icon.jpg가 없을 때 사용)"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("PIL이 설치되어 있지 않습니다. pip install pillow 를 실행해주세요.")
        return False
    
    script_dir = Path(__file__).parent
    iconset_dir = script_dir / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)
    
    for size in ICON_SIZES:
        # 이미지 생성
        img = Image.new('RGBA', (size, size), (74, 144, 217, 255))
        draw = ImageDraw.Draw(img)
        
        # 그라데이션 효과
        for y in range(size):
            alpha = int(255 * (1 - y / size * 0.3))
            for x in range(size):
                r, g, b, a = img.getpixel((x, y))
                img.putpixel((x, y), (r, g, b, alpha))
        
        # 둥근 모서리 (macOS 스타일)
        radius = size // 5
        
        # 원 그리기 (동전 모양)
        circle_radius = size // 3
        center = size // 2
        draw.ellipse(
            [center - circle_radius, center - circle_radius,
             center + circle_radius, center + circle_radius],
            fill=(255, 215, 0, 255),  # 금색
            outline=(218, 165, 32, 255),
            width=max(1, size // 40)
        )
        
        # ₩ 심볼
        try:
            font_size = size // 3
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        text = "₩"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (size - text_width) // 2
        text_y = (size - text_height) // 2 - size // 20
        draw.text((text_x, text_y), text, fill=(139, 69, 19, 255), font=font)
        
        # 파일 저장
        img.save(iconset_dir / f"icon_{size}x{size}.png")
        if size <= 512:
            img_2x = img.resize((size * 2, size * 2), Image.LANCZOS)
            img_2x.save(iconset_dir / f"icon_{size}x{size}@2x.png")
    
    print(f"아이콘 이미지가 생성되었습니다: {iconset_dir}")
    
    # iconutil로 icns 생성
    icns_path = script_dir / "icon.icns"
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
            check=True
        )
        print(f"아이콘 파일이 생성되었습니다: {icns_path}")
        
        import shutil
        shutil.rmtree(iconset_dir)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"iconutil 실행 실패: {e}")
        return False


def create_simple_svg():
    """SVG 아이콘 생성 (대체용)"""
    script_dir = Path(__file__).parent
    svg_path = script_dir / "icon.svg"
    
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="1024" height="1024" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#5BA0E8"/>
      <stop offset="100%" style="stop-color:#3A80C8"/>
    </linearGradient>
  </defs>
  
  <!-- 배경 -->
  <rect width="1024" height="1024" rx="200" fill="url(#bg)"/>
  
  <!-- 동전 -->
  <circle cx="512" cy="480" r="280" fill="#FFD700" stroke="#DAA520" stroke-width="12"/>
  
  <!-- 원화 심볼 -->
  <text x="512" y="540" font-family="Arial, sans-serif" font-size="320" 
        fill="#8B4513" text-anchor="middle" font-weight="bold">₩</text>
  
  <!-- 비행기 -->
  <path d="M750 700 L850 750 L750 800 L770 750 Z" fill="white" opacity="0.9"/>
  
  <!-- 글로벌 심볼 -->
  <circle cx="850" cy="200" r="80" fill="none" stroke="white" stroke-width="8" opacity="0.8"/>
  <ellipse cx="850" cy="200" rx="40" ry="80" fill="none" stroke="white" stroke-width="8" opacity="0.8"/>
  <line x1="770" y1="200" x2="930" y2="200" stroke="white" stroke-width="8" opacity="0.8"/>
</svg>'''
    
    with open(svg_path, 'w') as f:
        f.write(svg_content)
    
    print(f"SVG 아이콘이 생성되었습니다: {svg_path}")
    return svg_path


if __name__ == '__main__':
    print("🎨 여행 경비 정산 앱 아이콘 생성 중...")
    
    script_dir = Path(__file__).parent
    source_image = script_dir / "icon.jpg"
    
    # icon.jpg가 있으면 해당 이미지로 아이콘 생성
    if source_image.exists():
        print(f"📷 icon.jpg 이미지를 사용하여 아이콘을 생성합니다.")
        if not create_icon_from_jpg():
            print("\n❌ icon.jpg에서 아이콘 생성 실패. 기본 아이콘을 생성합니다.")
            if not create_icon_with_pil():
                print("\nPIL 아이콘 생성 실패. SVG 아이콘을 생성합니다.")
                create_simple_svg()
    else:
        # icon.jpg가 없으면 기본 아이콘 생성
        print("📷 icon.jpg가 없습니다. 기본 아이콘을 생성합니다.")
        if not create_icon_with_pil():
            print("\nPIL 아이콘 생성 실패. SVG 아이콘을 생성합니다.")
            create_simple_svg()
            print("\n📌 SVG를 icns로 변환하려면:")
            print("   1. https://cloudconvert.com/svg-to-icns 사용")
            print("   2. 또는 Xcode에서 Asset Catalog 사용")
