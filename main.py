
import json
import re
import sqlite3
import uuid
from pathlib import Path

import streamlit as st

# 저장 파일이 들어갈 위치
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

JSON_FILE = DATA_DIR / "saves.json"
SQLITE_FILE = DATA_DIR / "saves.db"

PLACES = [
    "교무실",
    "학생회실",
    "방송실",
    "공용 인쇄실",
    "최종 추리"
]

MODES = ["SQLite", "JSON", "Session State"]


# 처음 시작할 때의 게임 상태
def empty_progress():
    return {"place": 0, "clues": [], "memo": ""}


# 저장된 데이터 불러오기
def read_saved(mode, save_id):
    if mode == "JSON":
        if not JSON_FILE.exists():
            return None

        data = json.loads(
            JSON_FILE.read_text(encoding="utf-8")
        )
        return data.get(save_id)

    if mode == "SQLite":
        with sqlite3.connect(SQLITE_FILE) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS saves "
                "(save_id TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )

            row = conn.execute(
                "SELECT state FROM saves WHERE save_id = ?",
                (save_id,)
            ).fetchone()

        return json.loads(row[0]) if row else None

    return None


# 현재 게임 상태 자동 저장
def write_saved(mode, save_id, progress):
    if mode == "JSON":
        if JSON_FILE.exists():
            data = json.loads(
                JSON_FILE.read_text(encoding="utf-8")
            )
        else:
            data = {}

        data[save_id] = progress

        JSON_FILE.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    elif mode == "SQLite":
        with sqlite3.connect(SQLITE_FILE) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS saves "
                "(save_id TEXT PRIMARY KEY, state TEXT NOT NULL)"
            )

            conn.execute(
                "INSERT OR REPLACE INTO saves "
                "(save_id, state) VALUES (?, ?)",
                (
                    save_id,
                    json.dumps(progress, ensure_ascii=False)
                )
            )
            conn.commit()


# 화면 설정
st.set_page_config(
    page_title="추리게임 자동 저장 실험",
    page_icon="🕵️"
)

st.title("🕵️ 추리게임 자동 저장 실험")

st.write(
    "장소를 이동하거나 단서를 모으면 자동 저장됩니다. "
    "F5를 눌러 확인해 보세요."
)


# 실험 번호를 URL에 저장
save_id = st.query_params.get("save_id", "")

if not re.fullmatch(r"[a-f0-9]{12}", save_id):
    save_id = uuid.uuid4().hex[:12]
    st.query_params["save_id"] = save_id


# 저장 방식 선택
url_mode = st.query_params.get("mode", "SQLite")

if url_mode not in MODES:
    url_mode = "SQLite"

mode = st.radio(
    "저장 방식 선택",
    MODES,
    index=MODES.index(url_mode),
    horizontal=True
)

if st.query_params.get("mode") != mode:
    st.query_params["mode"] = mode

st.caption(
    "현재 페이지 주소를 저장하면 "
    "같은 실험 번호로 다시 접속할 수 있습니다."
)


# 접속 시 저장된 상태 자동 불러오기
active = (mode, save_id)

if st.session_state.get("active") != active:
    st.session_state.active = active

    st.session_state.progress = (
        read_saved(mode, save_id) or empty_progress()
    )

progress = st.session_state.progress


# 게임 화면
st.subheader("현재 진행 상황")

st.write(
    f"**장소:** {PLACES[progress['place']]}"
)

st.progress(
    (progress["place"] + 1) / len(PLACES)
)


# 장소 이동 시 자동 저장
if st.button(
    "다음 장소로 이동",
    disabled=progress["place"] == len(PLACES) - 1
):
    progress["place"] += 1

    write_saved(mode, save_id, progress)
    st.rerun()


# 단서 수집 시 자동 저장
clue = f"{PLACES[progress['place']]}에서 발견한 단서"

if st.button(
    "이 장소의 단서 수집",
    disabled=clue in progress["clues"]
):
    progress["clues"].append(clue)

    write_saved(mode, save_id, progress)
    st.rerun()


st.write(
    "**수집한 단서:**",
    ", ".join(progress["clues"]) or "없음"
)


# 추리 노트 변경 시 자동 저장
memo = st.text_area(
    "추리 노트 (입력 후 다른 곳을 클릭해 확정)",
    value=progress["memo"],
    key=f"memo_{mode}_{save_id}"
)

if memo != progress["memo"]:
    progress["memo"] = memo

    write_saved(mode, save_id, progress)


# 실험 결과 안내
st.divider()

if mode == "Session State":
    st.warning(
        "Session State 방식은 새로고침하면 "
        "진행 상황이 초기화됩니다."
    )

else:
    st.success(
        f"{mode} 방식: 진행 상태가 자동 저장됩니다. "
        "새로고침하면 저장된 상태를 불러옵니다."
    )


# 저장되는 데이터 확인
with st.expander("실제 저장되는 데이터 보기"):
    st.json(progress)


st.caption(
    "실험용 앱입니다. 같은 주소를 아는 사람은 "
    "저장 데이터를 볼 수 있으므로 개인정보를 입력하지 마세요. "
    "또한 Streamlit Community Cloud에서는 "
    "서버 재시작 후 로컬 저장 파일의 보존이 보장되지 않습니다."
)
