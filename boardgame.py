import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import ssl
import certifi
import requests
import io



CSV_URL = "https://docs.google.com/spreadsheets/d/1ueaOfCcMBZ6HqFRDlJc7mIJ9WhhJX09huXnGJj0goeE/export?format=csv"

# =====================
# Utils
# =====================
@st.cache_data
def load_data():
    import requests
    import io

    response = requests.get(CSV_URL, timeout=10)

    if response.status_code != 200:
        st.error(f"CSV取得失敗: {response.status_code}")
        return pd.DataFrame()

    content = response.content  # ←これが重要

    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")))
    except:
        df = pd.read_csv(io.StringIO(content.decode("cp932")))

    # 型処理
    bool_cols = ["known", "played", "owned"]
    for c in bool_cols:
        df[c] = df[c].astype(bool)

    int_cols = [
        "rating", "win_count", "lose_count",
        "min_p", "max_p", "min_t", "max_t"
    ]
    for c in int_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    if "comment" not in df.columns:
        df["comment"] = ""
    df["comment"] = df["comment"].fillna("").astype(str)

    return df

def save_data(df):
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )

        client = gspread.authorize(creds)

        sheet = client.open_by_key("1ueaOfCcMBZ6HqFRDlJc7mIJ9WhhJX09huXnGJj0goeE")
        worksheet = sheet.sheet1

        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())

        st.success("保存成功🔥")

    except Exception as e:
        st.error(f"保存失敗: {e}")

# =====================
# App
# =====================
st.set_page_config(page_title="ボードゲームDB", layout="wide")
st.title("🎲 ボードゲームDB")


st.markdown("""
<style>
/* 変な transform/zoom が当たってる環境でズレるのを軽減する狙い */
html, body {
  transform: none !important;
  zoom: 1 !important;
}

/* Streamlit 全体のコンテナにも念のため */
[data-testid="stAppViewContainer"] {
  transform: none !important;
}
</style>
""", unsafe_allow_html=True)

df = load_data()


df["name"] = df["name"].fillna("").astype(str)
df["genre"] = df["genre"].fillna("").astype(str)

# =====================
# Sidebar Filters
# =====================
with st.sidebar:
    st.header("🔍 フィルタ")

    keyword = st.text_input("ゲーム名検索")

    # --- ジャンル（縦1列ボタン） ---
    genres = sorted(df["genre"].dropna().unique().tolist())  # genre列から作成 

    # 初期状態：全選択
    if "genre_selected" not in st.session_state:
        st.session_state.genre_selected = {g: True for g in genres}

    # CSV更新でジャンル増減した場合に追従
    for g in genres:
        st.session_state.genre_selected.setdefault(g, True)
    for g in list(st.session_state.genre_selected.keys()):
        if g not in genres:
            del st.session_state.genre_selected[g]

    # 見出し（ALLの上、表示は「ジャンル」のみ）
    st.markdown("### ジャンル")

    # 見た目：選択=赤（primary）、未選択=白（secondary）＋横長
    st.markdown("""
    <style>
    button[kind="primary"]{
    background-color:#ff4d4f !important;
    color:white !important;
    border:1px solid #ff4d4f !important;
    }
    button[kind="primary"]:hover{ background-color:#e63b3d !important; }

    button[kind="secondary"]{
    background-color:white !important;
    color:black !important;
    border:1px solid #ddd !important;
    }
    button[kind="secondary"]:hover{ border-color:#bbb !important; }

    button{
    width:100% !important;
    white-space:nowrap !important;
    }
    </style>
    """, unsafe_allow_html=True)

    def _toggle_genre(g):
        st.session_state.genre_selected[g] = not st.session_state.genre_selected[g]

    def _toggle_all():
        all_selected = all(st.session_state.genre_selected.values()) if genres else True
        new_state = not all_selected
        for gg in genres:
            st.session_state.genre_selected[gg] = new_state

    # 全選択中ならALLも赤
    all_selected_now = all(st.session_state.genre_selected.values()) if genres else True
    st.button(
        "ALL",
        use_container_width=True,
        type=("primary" if all_selected_now else "secondary"),
        on_click=_toggle_all
    )

    # ジャンルボタン（縦1列で常に表示）
    for g in genres:
        selected = st.session_state.genre_selected.get(g, True)
        label = f"{g}" if selected else f"{g}"
        st.button(
            label,
            key=f"genre_btn_{g}",
            use_container_width=True,
            type=("primary" if selected else "secondary"),
            on_click=_toggle_genre,
            args=(g,),
        )

    # 選択ジャンルのリスト（OR条件に使う）
    genre_filter = [g for g, v in st.session_state.genre_selected.items() if v]



    st.divider()

    # --- 人数・時間 ---
    min_p, max_p = int(df["min_p"].min()), 14  # 
    players_range = st.slider("プレイ人数", min_p, max_p, (min_p, max_p))

    min_t, max_t = int(df["min_t"].min()), int(df["max_t"].max())  # 
    time_range = st.slider("プレイ時間（分）", min_t, max_t, (min_t, max_t))

    only_known = st.checkbox("気になる")
    only_played = st.checkbox("遊んだ")
    only_owned = st.checkbox("持ってる")

    st.divider()
    st.subheader("➕ 新規ゲーム追加")

    with st.form("add_game_form", clear_on_submit=True):
        new_name = st.text_input("ゲーム名（必須）")
        new_genre = st.text_input("ジャンル（手入力）")  # 手入力のみ

        c1, c2 = st.columns(2)
        with c1:
            new_min_p = st.number_input("最小人数", min_value=1, value=2, step=1)
            new_min_t = st.number_input("最小時間（分）", min_value=1, value=15, step=5)
        with c2:
            new_max_p = st.number_input("最大人数", min_value=1, value=4, step=1)
            new_max_t = st.number_input("最大時間（分）", min_value=1, value=30, step=5)

        submitted = st.form_submit_button("追加")

        if submitted:
            # バリデーション
            if not new_name.strip():
                st.error("ゲーム名は必須です。")
            elif new_name.strip() in df["name"].astype(str).values:
                st.error("同名のゲームが既に存在します（重複不可）。")
            elif not new_genre.strip():
                st.error("ジャンルを入力してください。")
            elif new_min_p > new_max_p:
                st.error("最小人数が最大人数を超えています。")
            elif new_min_t > new_max_t:
                st.error("最小時間が最大時間を超えています。")
            else:
                new_row = {
                    "name": new_name.strip(),
                    "genre": new_genre.strip(),
                    "min_p": int(new_min_p),
                    "max_p": int(new_max_p),
                    "min_t": int(new_min_t),
                    "max_t": int(new_max_t),
                    "known": False,
                    "played": False,
                    "owned": False,
                    "rating": 0,
                    "win_count": 0,
                    "lose_count": 0,
                    "comment": "",
                }

                df_added = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df_added)  # CSV保存＋cacheクリア 

                st.success(f"追加しました: {new_row['name']}")
                st.rerun()

    st.divider()
    st.subheader("🗑️ ゲーム削除")

    # 削除候補（名前順）
    delete_target = st.selectbox(
        "削除するゲームを選択",
        options=sorted(df["name"].astype(str).unique().tolist())
    )

    # 誤操作防止：チェックを入れたときだけ削除ボタンを有効化
    confirm_delete = st.checkbox("本当に削除する（元に戻せません）")

    if st.button("削除", type="primary", disabled=not confirm_delete):
        # dfから削除（nameが主キー前提）
        df2 = df[df["name"].astype(str) != str(delete_target)].copy()
        save_data(df2)
        st.success(f"削除しました: {delete_target}")
        st.rerun()


# ボタン状態から genre_filter（選択されているジャンルのリスト）を生成
genre_filter = [g for g, v in st.session_state.genre_selected.items() if v]

# =====================
# Filtering
# =====================
view = df.copy()

if keyword:
    view = view[view["name"].str.contains(keyword, case=False)]


# ジャンル（OR）
if genre_filter:
    view = view[view["genre"].isin(genre_filter)]

view = view[
    (view["min_p"] <= players_range[1]) &
    (view["max_p"] >= players_range[0])
]

view = view[
    (view["min_t"] <= time_range[1]) &
    (view["max_t"] >= time_range[0])
]


if only_known:
    view = view[view["known"]]
if only_played:
    view = view[view["played"]]
if only_owned:
    view = view[view["owned"]]

st.caption(f"表示件数: {len(view)}")

# =====================
# Editable Table
# =====================

# 行数に応じてテーブル高さを自動調整（スクロールなしで全部表示）
ROW_HEIGHT = 35    # 1行あたりの目安(px)
HEADER_HEIGHT = 38 # ヘッダー分(px)
PADDING = 12       # 余白(px)

table_height = HEADER_HEIGHT + PADDING + ROW_HEIGHT * (len(view) + 1)

column_order = [
    "name",
    "genre",
    "players",
    "playtime",
    "known",
    "played",
    "owned",
    "rating",
    "win_count",
    "lose_count",
    "comment",
]


def _players_disp(row):
    a, b = int(row["min_p"]), int(row["max_p"])
    return f"{a}人" if a == b else f"{a}〜{b}人"

def _time_disp(row):
    a, b = int(row["min_t"]), int(row["max_t"])
    return f"{a}分" if a == b else f"{a}〜{b}分"

view = view.copy()
view["players"] = view.apply(_players_disp, axis=1)
view["playtime"] = view.apply(_time_disp, axis=1)


edited = st.data_editor(
    view[column_order],
    column_order=column_order,
    column_config={
        "rating": st.column_config.SelectboxColumn(
            "★",
            options=[0, 1, 2, 3, 4, 5],
            help="0=未評価",
        ),
        "win_count": st.column_config.NumberColumn("勝ち", min_value=0, step=1),
        "lose_count": st.column_config.NumberColumn("負け", min_value=0, step=1),
        "known": st.column_config.CheckboxColumn("気になる"),
        "played": st.column_config.CheckboxColumn("遊んだ"),
        "owned": st.column_config.CheckboxColumn("持ってる"),
        "name": st.column_config.TextColumn("ゲーム", disabled=True),
        "genre": st.column_config.TextColumn("ジャンル", disabled=True),
        "players": st.column_config.TextColumn("人数", disabled=True),
        "playtime": st.column_config.TextColumn("時間", disabled=True),
        "comment": st.column_config.TextColumn("メモ"),
    },
    num_rows="fixed",
    use_container_width=True,
    hide_index=True,
    height=table_height,
    key="editor",
)

# =====================
# Apply changes
# =====================
# 実際に保存対象（編集対象）とする列だけ比較する
compare_cols = ["name", "known", "played", "owned", "rating", "win_count", "lose_count", "comment"]

# data_editorはdtypeがズレやすいので、比較前に型を揃える
before = view[compare_cols].copy()
after  = edited[compare_cols].copy()

# 型合わせ
for c in ["known", "played", "owned"]:
    before[c] = before[c].astype(bool)
    after[c]  = after[c].astype(bool)

for c in ["rating", "win_count", "lose_count"]:
    before[c] = pd.to_numeric(before[c], errors="coerce").fillna(0).astype(int)
    after[c]  = pd.to_numeric(after[c], errors="coerce").fillna(0).astype(int)

before["comment"] = before["comment"].fillna("").astype(str)
after["comment"]  = after["comment"].fillna("").astype(str)

# インデックス差でequalsが落ちないようにする
before = before.reset_index(drop=True)
after  = after.reset_index(drop=True)

if not after.equals(before):
    # played=True ⇒ known=True
    after.loc[after["played"], "known"] = True

    # nameをキーに安全に更新
    base = df.set_index("name")
    upd = after.set_index("name")
    base.update(upd)
    df = base.reset_index()

    save_data(df)
    st.toast("✅ 保存しました", icon="💾")