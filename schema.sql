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
    avatar_hash varchar,
    source INTEGER
);

create table if not exists posts(
    post_id integer primary key,
    comment_list_id integer,
    user_id integer,
    language varchar,
    code varchar,
    text varchar,
    text_tsv tsvector,
    posted timestamp,
    vote_plus integer,
    vote_minus integer,
    rating numeric,
    source INTEGER
);

create table if not exists comments(
    comment_id integer primary key,
    post_id integer,
    parent_id integer,
    user_id integer,
    text varchar,
    text_tsv tsvector,
    posted timestamp,
    vote_plus integer,
    vote_minus integer,
    rating numeric,
    source INTEGER
);


CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE OF text ON comments FOR EACH ROW EXECUTE PROCEDURE tsvector_update_trigger(text_tsv, 'pg_catalog.russian', text);
CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE OF text ON posts FOR EACH ROW EXECUTE PROCEDURE tsvector_update_trigger(text_tsv, 'pg_catalog.russian', text);

create index if not exists comments_posted on comments(posted);
CREATE INDEX IF NOT EXISTS weighted_tsv_idx_comments ON comments USING GIST (text_tsv);
CREATE INDEX IF NOT EXISTS weighted_tsv_idx_posts ON posts USING GIST (text_tsv);
CREATE INDEX IF NOT EXISTS user_names ON users(name);