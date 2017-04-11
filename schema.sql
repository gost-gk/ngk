create table if not exists sync_states(
    post_id integer primary key,
    last_comment_id integer,
    pending boolean,
    priority integer,
    synced timestamp,
    result varchar
);
