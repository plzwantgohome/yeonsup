
import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# 1. 실험 파일과 게임 기본 정보
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
JSON_FILE = DATA_DIR / "progress.json"
DB_FILE = DATA_DIR / "progress.db"

PLACES = ["교무실", "학생회실", "방송실", "공용 인쇄실", "최종 추리"]
MODES = ["Session State", "JSON", "SQLite"]


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def new_record():
    return {
        "place": 0,
        "clues": [],
        "memo": "",
        "updated_at": now_utc()
    }


# 2. JSON: 파일 전체를 읽고 다시 저장하는 방식
def read_json():
    if not JSON_FILE.exists():
        return {}

    return json.loads(
        JSON_FILE.read_text(encoding="utf-8")
    )


def write_json(records):
    JSON_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# 3. SQLite: 데이터를 두 개의 테이블에 나누어 저장
def open_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        "CREATE TABLE IF NOT EXISTS saves ("
        "save_id TEXT PRIMARY KEY, "
        "place INTEGER NOT NULL, "
        "memo TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )

    conn.execute(
        "CREATE TABLE IF NOT EXISTS clues ("
        "save_id TEXT NOT NULL, "
        "clue TEXT NOT NULL, "
        "PRIMARY KEY(save_id, clue), "
        "FOREIGN KEY(save_id) REFERENCES saves(save_id))"
    )

    conn.commit()
    return conn


# 4. 저장된 게임 기록 불러오기
def load_record(mode, save_id):
    if mode == "JSON":
        return read_json().get(save_id)

    if mode == "SQLite":
        with closing(open_db()) as conn:
            row = conn.execute(
                "SELECT place, memo, updated_at "
                "FROM saves WHERE save_id = ?",
                (save_id,)
            ).fetchone()

            if row is None:
                return None

            clues = conn.execute(
                "SELECT clue FROM clues "
                "WHERE save_id = ? ORDER BY clue",
                (save_id,)
            ).fetchall()

        return {
            "place": row[0],
            "memo": row[1],
            "updated_at": row[2],
            "clues": [item[0] for item in clues]
        }

    return None


# 5. 게임 상태 자동 저장
def save_record(mode, save_id, record):
    record["updated_at"] = now_utc()

    if mode == "JSON":
        records = read_json()
        records[save_id] = record
        write_json(records)

    elif mode == "SQLite":
        with closing(open_db()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO saves"
                    "(save_id, place, memo, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(save_id) DO UPDATE SET "
                    "place=excluded.place, "
                    "memo=excluded.memo, "
                    "updated_at=excluded.updated_at",
                    (
                        save_id,
                        record["place"],
                        record["memo"],
                        record["updated_at"]
                    )
                )

                conn.execute(
                    "DELETE FROM clues WHERE save_id = ?",
                    (save_id,)
                )

                conn.executemany(
                    "INSERT INTO clues(save_id, clue) "
                    "VALUES (?, ?)",
                    [
                        (save_id, clue)
                        for clue in record["clues"]
                    ]
                )


# 6. 선택한 기록만 수정
def update_selected_record(mode, save_id, place, memo):
    if mode == "JSON":
        records = read_json()

        records[save_id]["place"] = place
        records[save_id]["memo"] = memo
        records[save_id]["updated_at"] = now_utc()

        # JSON은 전체 파일을 다시 저장
        write_json(records)

    else:
        # SQLite는 SQL로 특정 행만 수정
        with closing(open_db()) as conn:
            with conn:
                conn.execute(
                    "UPDATE saves SET "
                    "place = ?, memo = ?, updated_at = ? "
                    "WHERE save_id = ?",
                    (place, memo, now_utc(), save_id)
                )


# 7. 저장 기록 검색
def search_records(mode, keyword, chosen_place):
    keyword = keyword.strip()

    if mode == "JSON":
        # 파일 전체를 읽고 반복문으로 검색
        found = []

        for save_id, record in read_json().items():
            content = " ".join(
                [save_id, record["memo"]] + record["clues"]
            ).casefold()

            if keyword.casefold() not in content:
                continue

            if (
                chosen_place != "전체"
                and record["place"] != PLACES.index(chosen_place)
            ):
                continue

            found.append({
                "ID": save_id,
                "장소": PLACES[record["place"]],
                "단서": ", ".join(record["clues"]),
                "메모": record["memo"]
            })

        return sorted(found, key=lambda x: x["ID"])

    # SQLite는 SQL 조건문으로 검색
    sql = (
        "SELECT s.save_id, s.place, s.memo, "
        "COALESCE(GROUP_CONCAT(c.clue, ', '), '') "
        "FROM saves AS s "
        "LEFT JOIN clues AS c ON s.save_id = c.save_id "
        "WHERE 1 = 1"
    )

    params = []

    if keyword:
        sql += (
            " AND (s.save_id LIKE ? "
            "OR s.memo LIKE ? "
            "OR EXISTS ("
            "SELECT 1 FROM clues AS x "
            "WHERE x.save_id = s.save_id "
            "AND x.clue LIKE ?))"
        )

        params.extend([f"%{keyword}%"] * 3)

    if chosen_place != "전체":
        sql += " AND s.place = ?"
        params.append(PLACES.index(chosen_place))

    sql += " GROUP BY s.save_id ORDER BY s.save_id"

    with closing(open_db()) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [
        {
            "ID": row[0],
            "장소": PLACES[row[1]],
            "단서": row[3],
            "메모": row[2]
        }
        for row in rows
    ]


# 8. 추리 노트 자동 저장
def remember_memo():
    st.session_state["record"]["memo"] = (
        st.session_state["memo_draft"]
    )

    save_record(
        st.session_state["active_mode"],
        st.session_state["active_id"],
        st.session_state["record"]
    )


# =========================
# 웹앱 화면
# =========================

st.set_page_config(
    page_title="게임 저장 방식 비교 실험",
    page_icon="🗂️"
)

st.title("🗂️ 추리게임 데이터 저장 방식 비교")

st.write(
    "게임 진행 상태 자동 저장 → F5 복원 → "
    "여러 기록 검색·수정 → 실제 데이터 구조 확인"
)

st.caption(
    "공개 실험용 앱입니다. "
    "실명, 비밀번호 등 개인정보를 입력하지 마세요."
)


# 9. 저장 방식 선택
url_mode = st.query_params.get("mode", "SQLite")

if url_mode not in MODES:
    url_mode = "SQLite"

mode = st.radio(
    "① 저장 방식",
    MODES,
    index=MODES.index(url_mode),
    horizontal=True
)

if st.query_params.get("mode") != mode:
    st.query_params["mode"] = mode


# 10. 게임 기록 고유 ID
save_id = st.query_params.get("save_id", "")

if not re.fullmatch(r"[a-f0-9]{12}", save_id):
    save_id = uuid.uuid4().hex[:12]
    st.query_params["save_id"] = save_id

st.write(f"**현재 기록 ID:** `{save_id}`")

if st.button("새 게임 기록 만들기"):
    st.query_params["save_id"] = uuid.uuid4().hex[:12]
    st.rerun()


# 11. 접속 시 자동 복원
active = (mode, save_id)

if st.session_state.get("active") != active:
    record = load_record(mode, save_id)

    if record is None:
        record = new_record()
        save_record(mode, save_id, record)

    st.session_state["record"] = record
    st.session_state["active"] = active
    st.session_state["active_mode"] = mode
    st.session_state["active_id"] = save_id
    st.session_state["memo_draft"] = record["memo"]

record = st.session_state["record"]


# 12. 게임 진행 실험
st.divider()
st.subheader("② 게임 진행: 자동 저장과 새로고침")

st.write(f"**현재 장소:** {PLACES[record['place']]}")

st.progress(
    (record["place"] + 1) / len(PLACES)
)

col1, col2, col3 = st.columns(3)

with col1:
    if st.button(
        "다음 장소",
        disabled=record["place"] == len(PLACES) - 1,
        use_container_width=True
    ):
        record["place"] += 1
        save_record(mode, save_id, record)
        st.rerun()

with col2:
    clue = f"{PLACES[record['place']]} 단서"

    if st.button(
        "단서 수집",
        disabled=clue in record["clues"],
        use_container_width=True
    ):
        record["clues"].append(clue)
        save_record(mode, save_id, record)
        st.rerun()

with col3:
    if st.button(
        "이 기록 초기화",
        use_container_width=True
    ):
        record = new_record()
        save_record(mode, save_id, record)

        st.session_state["record"] = record
        st.session_state["memo_draft"] = ""

        st.rerun()

st.write(
    "**수집한 단서:**",
    ", ".join(record["clues"]) or "없음"
)

st.text_area(
    "추리 노트",
    key="memo_draft",
    on_change=remember_memo,
    help="입력 후 Ctrl+Enter를 누르거나 입력창 밖을 클릭하면 저장합니다."
)

if mode == "Session State":
    st.warning(
        "Session State: 현재 화면에서는 유지되지만 "
        "F5 새로고침 후 초기화됩니다."
    )
else:
    st.success(
        f"{mode}: 자동 저장 중! "
        "F5를 누르면 같은 URL에서 기록을 다시 불러옵니다."
    )

with st.expander("현재 게임 진행 데이터 보기"):
    st.json(record)


# 13. 여러 기록 검색과 수정
st.divider()
st.subheader("③ 여러 기록 검색 · 특정 기록 수정")

if mode == "Session State":
    st.info(
        "여러 기록 검색·수정 실험은 "
        "JSON 또는 SQLite에서 진행합니다."
    )

else:
    keyword = st.text_input(
        "검색어 (기록 ID / 단서 / 추리 노트)",
        key=f"search_{mode}"
    )

    chosen_place = st.selectbox(
        "장소 필터",
        ["전체"] + PLACES,
        key=f"place_filter_{mode}"
    )

    found = search_records(mode, keyword, chosen_place)

    st.write(f"**검색 결과: {len(found)}건**")

    if found:
        st.dataframe(
            found,
            hide_index=True,
            use_container_width=True
        )

        selected = st.selectbox(
            "수정할 기록 선택",
            [row["ID"] for row in found],
            key=f"selected_{mode}"
        )

        selected_record = load_record(mode, selected)

        with st.form(
            key=f"edit_{mode}_{selected}_{selected_record['updated_at']}"
        ):
            edited_place = st.selectbox(
                "변경할 장소",
                PLACES,
                index=selected_record["place"]
            )

            edited_memo = st.text_input(
                "변경할 추리 노트",
                value=selected_record["memo"]
            )

            submitted = st.form_submit_button(
                "선택한 기록만 수정"
            )

        if submitted:
            update_selected_record(
                mode,
                selected,
                PLACES.index(edited_place),
                edited_memo
            )

            st.session_state.pop("active", None)
            st.rerun()

    else:
        st.info(
            "해당 조건의 기록이 없습니다. "
            "새 기록을 만들거나 검색 조건을 변경해 보세요."
        )

    if mode == "JSON":
        st.caption(
            "JSON 검색: 전체 파일을 읽고 "
            "파이썬 반복문으로 조건을 검사합니다."
        )

        st.code(
            "for save_id, record in read_json().items():\n"
            "    if keyword in record['memo']:\n"
            "        ...",
            language="python"
        )

    else:
        st.caption(
            "SQLite 검색: SQL WHERE 조건문으로 "
            "필요한 기록을 조회합니다."
        )

        st.code(
            "SELECT save_id, place, memo\n"
            "FROM saves\n"
            "WHERE memo LIKE ?;",
            language="sql"
        )

        st.caption(
            "기록 수정에는 실제로 "
            "UPDATE ... WHERE save_id = ? 명령을 사용합니다."
        )


# 14. 실제 저장 구조 비교
st.divider()
st.subheader("④ JSON 구조 ↔ SQLite 테이블 비교")

left, right = st.columns(2)

with left:
    st.markdown(
        "**JSON: 한 파일에 여러 게임 기록이 저장됨**"
    )

    st.json(read_json())

    st.caption(
        "검색·수정 시 JSON 파일 전체를 읽습니다."
    )

with right:
    st.markdown(
        "**SQLite: 서로 연결된 두 개의 테이블**"
    )

    with closing(open_db()) as conn:
        raw_saves = conn.execute(
            "SELECT save_id, place, memo "
            "FROM saves ORDER BY save_id"
        ).fetchall()

        raw_clues = conn.execute(
            "SELECT save_id, clue "
            "FROM clues ORDER BY save_id"
        ).fetchall()

    st.write("saves 테이블 (저장 정보)")

    st.dataframe(
        [
            {
                "ID": row[0],
                "장소 번호": row[1],
                "메모": row[2]
            }
            for row in raw_saves
        ],
        hide_index=True
    )

    st.write("clues 테이블 (수집한 단서)")

    st.dataframe(
        [
            {
                "ID": row[0],
                "단서": row[1]
            }
            for row in raw_clues
        ],
        hide_index=True
    )

    st.caption(
        "저장 ID로 연결된 행을 SQL로 검색·수정합니다."
    )


# 15. 라이브러리 의존성 확인
with st.expander(
    "⑤ requirements.txt에는 왜 streamlit만 적을까?"
):
    st.code("streamlit", language="text")

    st.write(
        "json, sqlite3, uuid, pathlib 등은 "
        "파이썬 표준 라이브러리이므로 "
        "별도로 설치할 필요가 없습니다."
    )


st.info(
    "실험 주의: JSON과 SQLite는 서버의 로컬 파일에 저장됩니다. "
    "Streamlit Community Cloud에서는 서버가 재시작되거나 "
    "교체될 때 기록이 보존된다고 보장할 수 없습니다. "
    "또한 이 앱에는 사용자 인증 기능이 없습니다."
)
