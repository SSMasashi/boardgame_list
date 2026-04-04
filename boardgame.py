import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
import requests
import io

# =====================
# Constants & Config
# =====================
CSV_URL = "https://docs.google.com/spreadsheets/d/1ueaOfCcMBZ6HqFRDlJc7mIJ9WhhJX09huXnGJj0goeE/export?format=csv"
SHEET_KEY = "1ueaOfCcMBZ6HqFRDlJc7mIJ9WhhJX09huXnGJj0goeE"

# =====================
# 1. Data Access Layer
# =====================
@st.cache_data()
def load_data():
    response = requests.get(CSV_URL, timeout=10)

    if response.status_code != 200:
        st.error(f"CSV取得失敗: {response.status_code}")
        return pd.DataFrame()

    content = response.content
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")))
    except:
        df = pd.read_csv(io.StringIO(content.decode("cp932")))

    if df.empty:
        return df

    # 型処理
    bool_cols = ["known", "played", "owned"]
    for c in bool_cols:
        if c in df.columns:
            df[c] = df[c].astype(bool)

    int_cols = ["win_count", "lose_count", "min_p", "max_p", "min_t", "max_t"]
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    if "comment" not in df.columns:
        df["comment"] = ""
    if "rating" not in df.columns:
        df["rating"] = ""
        
    df["comment"] = df["comment"].fillna("").astype(str)
    df["rating"] = df["rating"].fillna("").astype(str)

    return df

def save_data(df):
    if st.session_state.get("saving", False):
        return

    st.session_state.saving = True

    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=scope,
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY)
        worksheet = sheet.sheet1

        worksheet.clear()
        worksheet.resize(len(df) + 1)

        data_to_write = [df.columns.values.tolist()] + df.values.tolist()
        try:
            worksheet.update(values=data_to_write, range_name="A1")
        except TypeError:
            worksheet.update(data_to_write)

        st.toast("保存成功🔥")

    except Exception as e:
        st.error(f"保存失敗: {e}")
    finally:
        st.session_state.saving = False


# =====================
# 2. Formatters & Helpers
# =====================
def format_players_text(row):
    try:
        a, b = int(row["min_p"]), int(row["max_p"])
        return f"{a}人" if a == b else f"{a}〜{b}人"
    except:
        return ""

def format_time_text(row):
    try:
        a, b = int(row["min_t"]), int(row["max_t"])
        return f"{a}分" if a == b else f"{a}〜{b}分"
    except:
        return ""

def init_genre_state(genres):
    """ジャンル選択のセッションステートを初期化・整理する"""
    if "genre_selected" not in st.session_state:
        st.session_state.genre_selected = {g: False for g in genres}

    for g in genres:
        st.session_state.genre_selected.setdefault(g, False)

    for g in list(st.session_state.genre_selected.keys()):
        if g not in genres:
            del st.session_state.genre_selected[g]


# =====================
# 3. UI Components & Business Logic
# =====================
def setup_page():
    st.set_page_config(page_title="ボードゲームDB", layout="wide")
    st.markdown("""
    <style>
    html, body { transform: none !important; zoom: 1 !important; }
    [data-testid="stAppViewContainer"] { transform: none !important; }
    button[kind="primary"]{ background-color:#ff4d4f !important; color:white !important; border:1px solid #ff4d4f !important; }
    button[kind="primary"]:hover{ background-color:#e63b3d !important; }
    button[kind="secondary"]{ background-color:white !important; color:black !important; border:1px solid #ddd !important; }
    button[kind="secondary"]:hover{ border-color:#bbb !important; }
    button{ width:100% !important; white-space:nowrap !important; }
    </style>
    """, unsafe_allow_html=True)

def render_sidebar_filters(df):
    """フィルタUIを描画し、フィルタ条件の辞書を返す"""
    st.header("🔍 フィルタ")
    keyword = st.text_input("ゲーム名検索")

    # ジャンルフィルタ
    genres = sorted(df["genre"].dropna().unique().tolist()) 
    init_genre_state(genres)

    st.markdown("### ジャンル")

    def _toggle_genre(g):
        st.session_state.genre_selected[g] = not st.session_state.genre_selected[g]

    def _toggle_all():
        all_selected = all(st.session_state.genre_selected.values()) if genres else True
        new_state = not all_selected
        for gg in genres:
            st.session_state.genre_selected[gg] = new_state

    all_selected_now = all(st.session_state.genre_selected.values()) if genres else True
    st.button("ALL", use_container_width=True, type=("primary" if all_selected_now else "secondary"), on_click=_toggle_all)

    for g in genres:
        selected = st.session_state.genre_selected.get(g, True)
        st.button(g, key=f"genre_btn_{g}", use_container_width=True, type=("primary" if selected else "secondary"), on_click=_toggle_genre, args=(g,))

    genre_filter = [g for g, v in st.session_state.genre_selected.items() if v]
    st.divider()

    # 人数・時間・フラグ
    min_p_val = int(df["min_p"].min()) if not df["min_p"].empty else 1
    min_t_val = int(df["min_t"].min()) if not df["min_t"].empty else 1
    max_t_val = int(df["max_t"].max()) if not df["max_t"].empty else 60

    min_p, max_p = min_p_val, max(14, min_p_val) 
    players_range = st.slider("プレイ人数", min_p, max_p, (min_p, max_p))

    min_t, max_t = min_t_val, max_t_val
    time_range = st.slider("プレイ時間（分）", min_t, max_t, (min_t, max_t))

    only_known = st.checkbox("気になる")
    only_played = st.checkbox("遊んだ")
    only_owned = st.checkbox("持ってる")

    return {
        "keyword": keyword,
        "genres": genre_filter,
        "players": players_range,
        "time": time_range,
        "only_known": only_known,
        "only_played": only_played,
        "only_owned": only_owned
    }

def render_sidebar_actions(df):
    """追加・削除のUIを描画し、処理を実行する"""
    # 新規追加フォーム
    st.subheader("➕ 新規ゲーム追加")
    with st.form("add_game_form", clear_on_submit=True):
        new_name = st.text_input("ゲーム名（必須）")
        genre_options = sorted(df["genre"].dropna().unique().tolist())
        new_genre = st.selectbox("ジャンル", genre_options) if genre_options else st.text_input("ジャンル")

        c1, c2 = st.columns(2)
        with c1:
            new_min_p = st.number_input("最小人数", min_value=1, value=2, step=1)
            new_min_t = st.number_input("最小時間（分）", min_value=1, value=15, step=5)
        with c2:
            new_max_p = st.number_input("最大人数", min_value=1, value=4, step=1)
            new_max_t = st.number_input("最大時間（分）", min_value=1, value=30, step=5)

        if st.form_submit_button("追加"):
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
                    "name": new_name.strip(), "genre": new_genre.strip(),
                    "min_p": int(new_min_p), "max_p": int(new_max_p),
                    "min_t": int(new_min_t), "max_t": int(new_max_t),
                    "known": False, "played": False, "owned": False,
                    "rating": "", "win_count": 0, "lose_count": 0, "comment": "",
                }
                df_added = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(df_added)
                st.success(f"追加しました: {new_row['name']}")
                st.cache_data.clear()
                st.rerun()

    st.divider()
    
    # 削除アクション
    st.subheader("🗑️ ゲーム削除")
    delete_target = st.selectbox("削除するゲームを選択", options=sorted(df["name"].astype(str).unique().tolist()))
    confirm_delete = st.checkbox("本当に削除する（元に戻せません）")

    if st.button("削除", type="primary", disabled=not confirm_delete):
        df_deleted = df[df["name"].str.strip() != str(delete_target).strip()].copy()
        save_data(df_deleted)
        st.cache_data.clear()
        st.success(f"削除しました: {delete_target}")
        st.rerun()

def apply_filters(df, filters):
    """辞書のフィルタ条件を元にデータフレームを絞り込む"""
    view = df.copy()
    if filters["keyword"]:
        view = view[view["name"].str.contains(filters["keyword"], case=False)]
    if filters["genres"]:
        view = view[view["genre"].isin(filters["genres"])]
        
    view = view[
        (view["min_p"] <= filters["players"][1]) & (view["max_p"] >= filters["players"][0])
    ]
    view = view[
        (view["min_t"] <= filters["time"][1]) & (view["max_t"] >= filters["time"][0])
    ]
    if filters["only_known"]: view = view[view["known"]]
    if filters["only_played"]: view = view[view["played"]]
    if filters["only_owned"]: view = view[view["owned"]]
    return view

def process_inline_save(full_df, edited_df):
    """エディタからの変更を安全にメインデータへマージして保存する"""
    editable_cols = ["known", "played", "owned", "rating", "comment"]

    for c in ["known", "played", "owned"]:
        edited_df[c] = edited_df[c].astype(bool)

    edited_df["comment"] = edited_df["comment"].fillna("").astype(str)
    edited_df["rating"]  = edited_df["rating"].fillna("").astype(str)

    # In-placeで安全に更新（ソート順序を破壊せず、表示用列も混入させない）
    full_df.set_index("name", inplace=True)
    edited_df.set_index("name", inplace=True)
    
    full_df.update(edited_df[editable_cols])

    new_df = full_df.reset_index()
    save_data(new_df)
    st.cache_data.clear()


# =====================
# 4. Main Application Flow
# =====================
def main():
    setup_page()
    st.title("🎲 ボードゲームDB")

    # データ読み込み・前処理
    full_df = load_data()
    if full_df.empty:
        st.warning("スプレッドシートにデータがありません。")
        st.stop()

    full_df["name"] = full_df["name"].fillna("").astype(str)
    full_df["genre"] = full_df["genre"].fillna("").astype(str)

    # サイドバーの構築
    with st.sidebar:
        filters = render_sidebar_filters(full_df)
        st.divider()
        render_sidebar_actions(full_df)

    # フィルタ適用と表示用データ作成
    view_df = apply_filters(full_df, filters)
    view_df["players"] = view_df.apply(format_players_text, axis=1) if not view_df.empty else []
    view_df["playtime"] = view_df.apply(format_time_text, axis=1) if not view_df.empty else []

    # メインコントロール部（保存ボタンのキャッチをここで事前に行う）
    left, right = st.columns([8, 1])
    with left:
        st.caption(f"表示件数: {len(view_df)}")
    with right:
        # st.button は押された瞬間のターンだけ True を返す。これでフラグ管理が不要になる
        do_save = st.button("💾 保存", type="primary")

    # テーブルエディタの描画
    ROW_HEIGHT, HEADER_HEIGHT, PADDING = 35, 38, 12
    table_height = HEADER_HEIGHT + PADDING + ROW_HEIGHT * (len(view_df) + 1)
    column_order = ["name", "genre", "players", "playtime", "known", "played", "owned", "rating", "comment"]

    edited_df = st.data_editor(
        view_df[column_order],
        column_order=column_order,
        column_config={
            "rating": st.column_config.SelectboxColumn("★", options=["", "★", "★★", "★★★", "★★★★", "★★★★★"]),
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

    # テーブル描画直後に保存処理を実行（do_saveがTrueの場合のみ）
    if do_save:
        process_inline_save(full_df, edited_df)
        st.rerun()

if __name__ == "__main__":
    main()