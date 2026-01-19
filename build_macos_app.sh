#!/bin/bash
#
# macOS 앱 빌드 스크립트
# 여행 경비 정산 앱을 .app 번들 및 .dmg 파일로 패키징합니다.
#

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  여행 경비 정산 앱 - macOS 빌드 스크립트${NC}"
echo -e "${BLUE}========================================${NC}"

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# 리소스 폴더 생성
echo -e "\n${YELLOW}[1/6] 리소스 폴더 준비 중...${NC}"
mkdir -p resources

# 아이콘이 없으면 기본 아이콘 생성
if [ ! -f "resources/icon.icns" ]; then
    echo -e "${YELLOW}  아이콘 파일이 없습니다. 기본 아이콘을 생성합니다...${NC}"
    
    # 임시 아이콘 생성 (sips 사용)
    mkdir -p resources/icon.iconset
    
    # PNG 아이콘 생성 (AppleScript 사용)
    /usr/bin/osascript << 'EOF'
tell application "Image Events"
    launch
end tell
EOF
    
    # 간단한 텍스트 기반 아이콘 생성
    for size in 16 32 64 128 256 512 1024; do
        if command -v convert &> /dev/null; then
            # ImageMagick이 있으면 사용
            convert -size ${size}x${size} xc:#4A90D9 \
                -font Arial -pointsize $((size/4)) \
                -fill white -gravity center \
                -annotate +0+0 "💰" \
                "resources/icon.iconset/icon_${size}x${size}.png" 2>/dev/null || true
        fi
    done
    
    # iconutil로 icns 생성 (iconset이 있으면)
    if [ -d "resources/icon.iconset" ] && [ "$(ls -A resources/icon.iconset)" ]; then
        iconutil -c icns resources/icon.iconset -o resources/icon.icns 2>/dev/null || true
        rm -rf resources/icon.iconset
    fi
    
    # 기본 아이콘이 없으면 시스템 아이콘 사용
    if [ ! -f "resources/icon.icns" ]; then
        echo -e "${YELLOW}  기본 시스템 아이콘을 사용합니다.${NC}"
        cp /System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns resources/icon.icns 2>/dev/null || true
    fi
fi

# React 프론트엔드 빌드
echo -e "\n${YELLOW}[2/6] React 프론트엔드 빌드 중...${NC}"
cd frontend

# node_modules가 없으면 설치
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}  npm 패키지 설치 중...${NC}"
    npm install
fi

# API 경로를 상대 경로로 변경하여 빌드
# 환경 변수로 설정
export REACT_APP_API_BASE=""

# package.json에 homepage 추가 (상대 경로용)
if ! grep -q '"homepage"' package.json; then
    sed -i '' 's/"private": true,/"private": true,\n  "homepage": ".",/' package.json
fi

npm run build

cd "$PROJECT_ROOT"

# Python 가상환경 활성화 및 의존성 설치
echo -e "\n${YELLOW}[3/6] Python 환경 준비 중...${NC}"
if [ -d "VENV" ]; then
    source VENV/bin/activate
else
    echo -e "${RED}  가상환경(VENV)을 찾을 수 없습니다.${NC}"
    echo -e "${YELLOW}  새 가상환경을 생성합니다...${NC}"
    python3 -m venv VENV
    source VENV/bin/activate
    pip install -r backend/requirements.txt
fi

# PyInstaller 설치
echo -e "${YELLOW}  PyInstaller 설치/업데이트 중...${NC}"
pip install pyinstaller --quiet

# 기존 빌드 결과물 정리
echo -e "\n${YELLOW}[4/6] 이전 빌드 결과물 정리 중...${NC}"
rm -rf build dist

# PyInstaller로 앱 빌드
echo -e "\n${YELLOW}[5/6] PyInstaller로 앱 빌드 중...${NC}"
echo -e "${YELLOW}  이 과정은 몇 분 정도 걸릴 수 있습니다...${NC}"

# spec 파일의 아이콘 경로 확인 및 수정
if [ -f "resources/icon.icns" ]; then
    ICON_PATH="resources/icon.icns"
else
    ICON_PATH=""
fi

pyinstaller TourExpense.spec --noconfirm

# DMG 생성
echo -e "\n${YELLOW}[6/6] DMG 파일 생성 중...${NC}"

APP_PATH="dist/TourExpense.app"
DMG_NAME="TourExpense-1.0.0"
DMG_PATH="dist/${DMG_NAME}.dmg"
DMG_TEMP_PATH="dist/${DMG_NAME}-temp.dmg"

if [ -d "$APP_PATH" ]; then
    # 임시 폴더 생성
    mkdir -p dist/dmg-contents
    cp -R "$APP_PATH" dist/dmg-contents/
    
    # Applications 폴더 심볼릭 링크 생성
    ln -sf /Applications dist/dmg-contents/Applications
    
    # README 파일 생성
    cat > dist/dmg-contents/README.txt << 'README'
═══════════════════════════════════════════════════════════
               🌏 여행 경비 정산 앱 v1.0.0
═══════════════════════════════════════════════════════════

설치 방법:
1. TourExpense.app 을 Applications 폴더로 드래그하세요.
2. Applications 폴더에서 TourExpense 를 실행하세요.

처음 실행 시 주의사항:
- "확인되지 않은 개발자" 경고가 나타나면:
  1. 시스템 환경설정 > 보안 및 개인정보 보호 로 이동
  2. "TourExpense" 앱 열기를 허용하세요.

사용 방법:
- 앱 실행 시 자동으로 브라우저가 열립니다.
- 영수증 이미지를 드래그하면 자동으로 분석됩니다.
- OpenAI API 키를 설정하면 더 정확한 분석이 가능합니다.

문의: https://github.com/your-repo/tour_expense

═══════════════════════════════════════════════════════════
README
    
    # DMG 생성 (hdiutil 사용)
    echo -e "${YELLOW}  DMG 파일을 생성하는 중...${NC}"
    
    # 기존 DMG 삭제
    rm -f "$DMG_PATH" "$DMG_TEMP_PATH"
    
    # DMG 크기 계산 (앱 크기 + 여유 공간)
    APP_SIZE=$(du -sm dist/dmg-contents | cut -f1)
    DMG_SIZE=$((APP_SIZE + 50))
    
    # 임시 DMG 생성
    hdiutil create -srcfolder dist/dmg-contents \
        -volname "TourExpense" \
        -fs HFS+ \
        -fsargs "-c c=64,a=16,e=16" \
        -format UDRW \
        -size ${DMG_SIZE}m \
        "$DMG_TEMP_PATH"
    
    # DMG 마운트
    MOUNT_DIR=$(hdiutil attach -readwrite -noverify -noautoopen "$DMG_TEMP_PATH" | grep -E '/Volumes/' | sed 's/.*\/Volumes/\/Volumes/')
    
    # 배경 및 아이콘 위치 설정 (AppleScript)
    /usr/bin/osascript << EOF
tell application "Finder"
    tell disk "TourExpense"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {400, 100, 920, 440}
        set theViewOptions to the icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 80
        set position of item "TourExpense.app" of container window to {130, 150}
        set position of item "Applications" of container window to {390, 150}
        set position of item "README.txt" of container window to {260, 280}
        close
        open
        update without registering applications
        delay 2
        close
    end tell
end tell
EOF
    
    # DMG 언마운트
    sync
    hdiutil detach "$MOUNT_DIR" -quiet
    
    # 최종 DMG 압축
    hdiutil convert "$DMG_TEMP_PATH" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH"
    
    # 임시 파일 정리
    rm -f "$DMG_TEMP_PATH"
    rm -rf dist/dmg-contents
    
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ 빌드가 완료되었습니다!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "\n📦 생성된 파일:"
    echo -e "   - 앱: ${BLUE}${APP_PATH}${NC}"
    echo -e "   - DMG: ${BLUE}${DMG_PATH}${NC}"
    echo -e "\n💡 DMG 파일을 배포하거나 앱을 직접 Applications 폴더에 복사할 수 있습니다."
else
    echo -e "${RED}  ❌ 앱 빌드에 실패했습니다.${NC}"
    exit 1
fi
