#!/usr/bin/env bash
set -o errexit

pip install -r backend/requirements.txt

cd frontend
npm install
npm run build
cd ..

rm -rf backend/static
cp -r frontend/build backend/static
