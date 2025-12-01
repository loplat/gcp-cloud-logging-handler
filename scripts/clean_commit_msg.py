#!/usr/bin/env python3
import sys

def main():
    # commit-msg 훅은 커밋 메시지가 저장된 파일의 경로를 첫 번째 인자로 받습니다.
    commit_msg_filepath = sys.argv[1]
    
    try:
        with open(commit_msg_filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return

    lines = content.splitlines()
    new_lines = []
    for line in lines:
        # Claude Code 관련 서명 제거
        if "Generated with" in line:
            continue
        if "Co-Authored-By" in line:
            continue
        new_lines.append(line)

    # 끝부분의 불필요한 공백 라인 제거
    while new_lines and not new_lines[-1].strip():
        new_lines.pop()

    # 파일 다시 쓰기
    with open(commit_msg_filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')

if __name__ == "__main__":
    main()

