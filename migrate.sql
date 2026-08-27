-- 既有資料庫升級用。在 Supabase SQL Editor 執行一次即可，重複執行也安全。

-- 大餐目標金額（!算帳 沒帶數字時的預設；LIFF「大餐目標」卡片會寫這欄）
alter table groups add column if not exists dinner_target_twd integer;

-- 聚餐算帳事件（!算帳 每次會寫一筆）
create table if not exists dinner_events (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    title text not null,
    total_amount integer not null,
    created_at timestamptz not null default now()
);

-- 讓 PostgREST 立刻看到新欄位／新表（Supabase 通常會自動 reload，這行是保險）
notify pgrst, 'reload schema';
