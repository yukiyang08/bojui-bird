create table groups (
    id uuid primary key default gen_random_uuid(),
    line_group_id text not null unique,
    point_value_twd integer not null default 100,
    created_at timestamptz not null default now()
);
-- 大餐目標金額不放這裡，存在 dinner_events 中 title = '大餐目標' 的那一列
-- （每組一列、會被覆蓋）。!算帳 沒帶數字時讀它。

create table group_members (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    line_user_id text not null,
    display_name text,
    total_points integer not null default 0,
    unique (group_id, line_user_id)
);

create table point_records (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    target_user_id text not null,
    recorder_user_id text not null,
    delta integer not null,
    reason text,
    created_at timestamptz not null default now()
);

create index point_records_group_target_idx
    on point_records (group_id, target_user_id, created_at desc);

-- 每次 !算帳 記一列（title = 聚餐名稱）；另外 title = '大餐目標' 的那一列
-- 存的是該群組目前設定的大餐目標金額（!目標 / LIFF 設定會覆蓋它）
create table dinner_events (
    id uuid primary key default gen_random_uuid(),
    group_id uuid not null references groups(id),
    title text not null,
    total_amount integer not null,
    created_at timestamptz not null default now()
);
