
import json
import re
import sqlite3
from pathlib import Path

import streamlit as st

# 이 폴더에 테스트용 저장 파일을 만듭니다.
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
JSON_PATH = DATA_DIR / "saves.json"
DB_PATH = DATA_DIR / "saves.db"

PLACES = ["교무실", "학생회실", "인쇄실", "최종 추리"]
MODES = ["Session State", "JSON 파일", "SQLite 데이터베이스"]


def new_progress():
    return {"place": 0, "clues": [], "memo": ""}


def save_json(slot, progress):
    if JSON_PATH.exists():
        records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    else:
        records = {}

    records[slot] = progress

    JSON_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_json(slot):
    if not JSON_PATH.exists():
        return None

    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    return records.get(slot)


def save_sqlite(slot, progress):
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS saves "
            "(slot TEXT PRIMARY KEY, progress_json TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO saves(slot, progress_json) VALUES (?, ?)",
            (slot, json.dumps(progress, ensure_ascii=False)),
        )
        connection.commit()


def load_sqlite(slot):
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS saves "
            "(slot TEXT PRIMARY KEY, progress_json TEXT NOT NULL)"
        )

        result = connection.execute(
            "SELECT progress_json FROM saves WHERE slot = ?",
            (slot,)
        ).fetchone()

    return json.loads(result[0]) if result else None


def load_progress(mode, slot):
    if mode == "JSON 파일":
        return load_json(slot)

    if mode == "SQLite 데이터베이스":
        return load_sqlite(slot)

    return None


def save_progress(mode, slot, progress):
    if mode == "JSON 파일":
        save_json(slot, progress)

    elif mode == "SQLite 데이터베이스":
        save_sqlite(slot, progress)


st.set_page_config(
    page_title="추리게임 데이터 저장 실험실",
    page_icon="🗂️"
)

st.title("🗂️ 추리게임 데이터 저장 실험실")

st.write(
    "진행 위치·조사 기록·추리 노트를 저장하고 "
    "새로고침 후 복원해 보세요."
)

st.caption(
    "학습용 공개 실험입니다. "
    "실명·비밀번호·개인정보는 입력하지 마세요."
)

mode = st.radio(
    "① 저장 방식",
    MODES,
    horizontal=True
)

slot = st.text_input(
    "② 실험 슬롯 ID (영문·숫자·-·_만 사용)",
    value="test01"
)

if not re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", slot):
    st.error("슬롯 ID를 영문·숫자·-·_로 1~20자 입력하세요.")
    st.stop()


# 저장 방식이나 슬롯을 바꾸면
# 화면의 임시 진행 상태를 새로 시작합니다.
active = (mode, slot)

if st.session_state.get("active") != active:
    st.session_state.active = active
    st.session_state.progress = new_progress()
    st.session_state.memo_version = (
        st.session_state.get("memo_version", 0) + 1
    )


progress = st.session_state.progress

st.divider()
st.subheader("③ 모의 추리게임")

st.write(
    f"**현재 장소:** {PLACES[progress['place']]} "
    f"({progress['place'] + 1}/4)"
)

st.progress((progress["place"] + 1) / 4)


left, right = st.columns(2)

with left:
    if st.button(
        "다음 장소로",
        disabled=progress["place"] >= 3,
        use_container_width=True
    ):
        progress["place"] += 1
        st.rerun()

with right:
    if st.button(
        "화면 상태 초기화",
        use_container_width=True
    ):
        st.session_state.progress = new_progress()
        st.session_state.memo_version += 1
        st.rerun()


clue = f"{PLACES[progress['place']]} 단서"

if st.button(
    "현재 장소의 단서 수집",
    disabled=clue in progress["clues"]
):
    progress["clues"].append(clue)
    st.rerun()


note_key = f"memo_draft_{st.session_state.memo_version}"

st.text_input(
    "추리 노트 입력",
    value=progress["memo"],
    key=note_key
)

if st.button("추리 노트에 반영"):
    progress["memo"] = st.session_state[note_key]

    st.success(
        "현재 화면 상태에 메모를 반영했어요. "
        "저장 버튼은 별도로 눌러야 해요."
    )


st.write(
    "**수집한 단서:**",
    ", ".join(progress["clues"]) or "없음"
)

st.write(
    "**추리 노트:**",
    progress["memo"] or "비어 있음"
)


st.divider()
st.subheader("④ 저장 및 복원")

if mode == "Session State":
    st.info(
        "버튼을 누르는 동안 현재 세션에서 유지됩니다. "
        "새로고침하면 초기화됩니다."
    )

else:
    st.caption(
        "현재 장소와 단서, 노트가 모두 저장됩니다. "
        "저장 후 새로고침하고 다시 불러오세요."
    )


col_save, col_load = st.columns(2)

with col_save:
    if st.button(
        "현재 상태 저장",
        use_container_width=True
    ):
        if mode == "Session State":
            st.info(
                "Session State는 지금 세션에 "
                "이미 저장되어 있어요."
            )

        else:
            save_progress(mode, slot, progress)
            st.success(f"{mode}에 저장했어요.")


with col_load:
    if st.button(
        "저장 상태 불러오기",
        use_container_width=True
    ):
        if mode == "Session State":
            st.warning(
                "Session State는 새 세션에서 "
                "이전 상태를 불러올 수 없어요."
            )

        else:
            saved = load_progress(mode, slot)

            if saved is None:
                st.warning(
                    "이 슬롯에 저장된 데이터가 없어요."
                )

            else:
                st.session_state.progress = saved
                st.session_state.memo_version += 1
                st.rerun()


with st.expander("현재 진행 상태의 데이터 구조 확인"):
    st.json(progress)


st.caption(
    "주의: JSON/SQLite는 이 서버의 로컬 파일에 저장됩니다. "
    "Streamlit Community Cloud에서는 서버 교체·재시작 후 "
    "파일 보존이 보장되지 않습니다."
)
