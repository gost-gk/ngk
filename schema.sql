create table if not exists sync_states(
    post_id integer primary key,
    last_comment_id integer,
    pending boolean,
    priority integer,
    synced timestamp,
    result varchar
);

create table if not exists users(
    user_id integer primary key,
    name varchar,
    avatar_hash varchar
);

create table if not exists posts(
    post_id integer primary key,
    comment_list_id integer,
    user_id integer,
    language varchar,
    code varchar,
    text varchar,
    posted timestamp,
    vote_plus integer,
    vote_minus integer,
    rating numeric
);

create table if not exists comments(
    comment_id integer primary key,
    post_id integer,
    parent_id integer,
    user_id integer,
    text varchar,
    posted timestamp,
    vote_plus integer,
    vote_minus integer,
    rating numeric
);

create index if not exists comments_posted on comments(posted);
