-- 既有資料庫升級用。在 Supabase SQL Editor 執行一次即可，重複執行也安全。

-- 聚餐算帳事件（!算帳 每次寫一筆；title = '大餐目標' 的那筆存目前的大餐目標金額）
create table if not exists dinner_events (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    title text not null,
    total_amount integer not null,
    created_at timestamptz not null default now()
);

-- @不揪鳥 閒聊的對話紀錄，每人每群組一條線，讀最近幾筆餵給 Gemini 當上下文
create table if not exists chat_history (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    line_user_id text not null,
    role text not null check (role in ('user', 'model')),
    text text not null,
    created_at timestamptz not null default now()
);

create index if not exists chat_history_group_user_idx
    on chat_history (group_id, line_user_id, created_at desc);

-- 讓 PostgREST 立刻看到新欄位／新表（Supabase 通常會自動 reload，這行是保險）
notify pgrst, 'reload schema';
