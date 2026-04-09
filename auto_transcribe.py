#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================
  통화 자동 변환 시스템 v1.0
  이상발 대표 전용 — 찐(Claude) 제작
  
  폴더를 감시하다가 오디오 파일이 추가되면
  자동으로 텍스트 변환 후 저장합니다.
====================================================
"""

import os
import sys
import time
import json
import requests
import threading
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ============================================================
#  ★ 설정 구역 — 여기만 수정하세요
# ============================================================

ASSEMBLYAI_KEY = "여기에_AssemblyAI_API_키_입력"

# 감시할 폴더 (녹음 파일이 저장되는 폴더)
WATCH_FOLDER = r"C:\Users\balsa\녹음폴더"

# 변환된 텍스트를 저장할 폴더
OUTPUT_FOLDER = r"C:\Users\balsa\변환텍스트"

# 지원 오디오 형식
AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.ogg', '.webm', '.aac', '.flac', '.mp4'}

# 변환 언어 (ko=한국어, en=영어)
LANGUAGE = "ko"

# 처리 완료된 파일 목록 저장 경로
PROCESSED_LOG = os.path.join(OUTPUT_FOLDER, "_처리완료목록.json")

# ============================================================


class Colors:
    """터미널 색상"""
    GREEN  = '\033[92m'
    YELLOW = '\033[93m'
    RED    = '\033[91m'
    BLUE   = '\033[94m'
    CYAN   = '\033[96m'
    BOLD   = '\033[1m'
    RESET  = '\033[0m'


def log(msg, color=Colors.RESET):
    now = datetime.now().strftime('%H:%M:%S')
    print(f"{color}[{now}] {msg}{Colors.RESET}")


def load_processed():
    """처리 완료 목록 로드"""
    if os.path.exists(PROCESSED_LOG):
        with open(PROCESSED_LOG, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()


def save_processed(processed_set):
    """처리 완료 목록 저장"""
    with open(PROCESSED_LOG, 'w', encoding='utf-8') as f:
        json.dump(list(processed_set), f, ensure_ascii=False)


def upload_audio(file_path):
    """AssemblyAI에 파일 업로드"""
    log(f"  ① 파일 업로드 중: {os.path.basename(file_path)}", Colors.CYAN)
    headers = {'authorization': ASSEMBLYAI_KEY}
    with open(file_path, 'rb') as f:
        resp = requests.post(
            'https://api.assemblyai.com/v2/upload',
            headers=headers,
            data=f,
            timeout=300
        )
    resp.raise_for_status()
    return resp.json()['upload_url']


def request_transcription(audio_url):
    """변환 요청"""
    log("  ② 음성→텍스트 변환 요청 중...", Colors.CYAN)
    headers = {
        'authorization': ASSEMBLYAI_KEY,
        'content-type': 'application/json'
    }
    payload = {
        'audio_url': audio_url,
        'language_code': LANGUAGE,
        'punctuate': True,
        'format_text': True
    }
    resp = requests.post(
        'https://api.assemblyai.com/v2/transcript',
        headers=headers,
        json=payload,
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()['id']


def poll_transcription(transcript_id):
    """변환 완료 대기 (폴링)"""
    headers = {'authorization': ASSEMBLYAI_KEY}
    dots = 0
    while True:
        resp = requests.get(
            f'https://api.assemblyai.com/v2/transcript/{transcript_id}',
            headers=headers,
            timeout=30
        )
        data = resp.json()
        status = data.get('status', '')

        dots = (dots + 1) % 4
        sys.stdout.write(f"\r  ③ 변환 중{'.' * dots}{'  ' * (4 - dots)} (상태: {status})  ")
        sys.stdout.flush()

        if status == 'completed':
            print()
            return data.get('text', '(텍스트 없음)')
        elif status == 'error':
            print()
            raise Exception(f"변환 오류: {data.get('error', '알 수 없는 오류')}")

        time.sleep(3)


def save_result(audio_path, transcript_text):
    """변환 결과 저장"""
    base_name = Path(audio_path).stem
    now = datetime.now()
    date_str = now.strftime('%Y%m%d_%H%M%S')

    # 파일명: 원본파일명_날짜.txt
    out_filename = f"{base_name}_{date_str}.txt"
    out_path = os.path.join(OUTPUT_FOLDER, out_filename)

    # 저장 내용
    content = f"""====================================================
  AI 통화 변환 결과
====================================================
원본 파일  : {os.path.basename(audio_path)}
변환 일시  : {now.strftime('%Y년 %m월 %d일 %H:%M:%S')}
언어       : {'한국어' if LANGUAGE == 'ko' else '영어'}
글자 수    : {len(transcript_text):,}자
====================================================

{transcript_text}

====================================================
  (끝)
====================================================
"""

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)

    return out_path


def process_audio_file(file_path):
    """오디오 파일 처리 메인 함수"""
    processed = load_processed()

    # 이미 처리한 파일이면 스킵
    if file_path in processed:
        return

    # 파일이 완전히 저장될 때까지 대기 (복사 중인 파일 방지)
    time.sleep(2)
    if not os.path.exists(file_path):
        return

    # 파일 크기 확인 (0바이트 방지)
    size = os.path.getsize(file_path)
    if size == 0:
        return

    log(f"\n{'='*50}", Colors.BOLD)
    log(f"🎵 새 파일 감지: {os.path.basename(file_path)}", Colors.YELLOW)
    log(f"   크기: {size/1024/1024:.2f} MB", Colors.YELLOW)

    try:
        # 1. 업로드
        audio_url = upload_audio(file_path)

        # 2. 변환 요청
        transcript_id = request_transcription(audio_url)

        # 3. 완료 대기
        transcript_text = poll_transcription(transcript_id)

        # 4. 저장
        out_path = save_result(file_path, transcript_text)

        # 5. 완료 기록
        processed.add(file_path)
        save_processed(processed)

        log(f"✅ 변환 완료!", Colors.GREEN)
        log(f"   저장 위치: {out_path}", Colors.GREEN)
        log(f"   텍스트 미리보기: {transcript_text[:100]}...", Colors.GREEN)
        log(f"\n💡 Claude에 파일 첨부 방법:", Colors.CYAN)
        log(f"   Claude 대화창 → 📎 클릭 → {out_path} 선택", Colors.CYAN)
        log(f"{'='*50}\n", Colors.BOLD)

    except Exception as e:
        log(f"❌ 오류 발생: {str(e)}", Colors.RED)
        log(f"   파일: {file_path}", Colors.RED)


class AudioFileHandler(FileSystemEventHandler):
    """폴더 감시 이벤트 핸들러"""

    def on_created(self, event):
        if event.is_directory:
            return
        ext = Path(event.src_path).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            # 별도 스레드에서 처리 (감시 블록 방지)
            t = threading.Thread(
                target=process_audio_file,
                args=(event.src_path,),
                daemon=True
            )
            t.start()

    def on_moved(self, event):
        """파일 이동/이름 변경 감지"""
        if event.is_directory:
            return
        ext = Path(event.dest_path).suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            t = threading.Thread(
                target=process_audio_file,
                args=(event.dest_path,),
                daemon=True
            )
            t.start()


def scan_existing_files():
    """시작 시 기존 미처리 파일 스캔"""
    processed = load_processed()
    existing = []
    for f in os.listdir(WATCH_FOLDER):
        fp = os.path.join(WATCH_FOLDER, f)
        ext = Path(fp).suffix.lower()
        if ext in AUDIO_EXTENSIONS and fp not in processed:
            existing.append(fp)

    if existing:
        log(f"\n📂 미처리 파일 {len(existing)}개 발견 — 순차 처리합니다", Colors.YELLOW)
        for fp in existing:
            process_audio_file(fp)
    else:
        log("📂 미처리 파일 없음", Colors.GREEN)


def main():
    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔══════════════════════════════════════════╗
║   🎙️  통화 자동 변환 시스템 v1.0         ║
║   이상발 대표 전용 — 찐(Claude) 제작      ║
╚══════════════════════════════════════════╝
{Colors.RESET}""")

    # 설정 확인
    if ASSEMBLYAI_KEY == "여기에_AssemblyAI_API_키_입력":
        log("❌ AssemblyAI API 키를 설정하세요!", Colors.RED)
        log("   auto_transcribe.py 파일에서 ASSEMBLYAI_KEY 수정", Colors.RED)
        sys.exit(1)

    # 폴더 생성
    os.makedirs(WATCH_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    log(f"📂 감시 폴더: {WATCH_FOLDER}", Colors.BLUE)
    log(f"💾 저장 폴더: {OUTPUT_FOLDER}", Colors.BLUE)
    log(f"🌐 언어: {'한국어' if LANGUAGE == 'ko' else '영어'}", Colors.BLUE)
    log(f"🎵 지원 형식: {', '.join(AUDIO_EXTENSIONS)}", Colors.BLUE)

    # 기존 미처리 파일 처리
    scan_existing_files()

    # 폴더 감시 시작
    event_handler = AudioFileHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    observer.start()

    log(f"\n👀 폴더 감시 시작! 새 녹음 파일을 감지하면 자동 변환합니다", Colors.GREEN)
    log(f"   종료: Ctrl+C\n", Colors.GREEN)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("\n⏹️  시스템 종료", Colors.YELLOW)
        observer.stop()
    observer.join()


if __name__ == '__main__':
    main()
