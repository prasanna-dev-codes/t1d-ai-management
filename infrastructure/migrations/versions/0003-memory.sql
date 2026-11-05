CREATE TABLE memory_episodes (
 id uuid PRIMARY KEY,
 study_id uuid NOT NULL,
 patient_id uuid NOT NULL,
 anchor_id uuid NOT NULL,
 definition_version text NOT NULL,
 definition_hash text NOT NULL CHECK (definition_hash ~ '^[0-9a-f]{64}$'),
 content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
 start_at timestamptz NOT NULL,
 end_at timestamptz NOT NULL CHECK (end_at>start_at),
 available_at timestamptz NOT NULL DEFAULT clock_timestamp() CHECK (available_at>=end_at),
 tombstoned boolean NOT NULL DEFAULT false,
 manifest jsonb NOT NULL,
 embedding vector(64) NOT NULL,
 embedding_version text NOT NULL CHECK (embedding_version='food-hash64-v1'),
 FOREIGN KEY (patient_id,study_id) REFERENCES patients(id,study_id),
 FOREIGN KEY (anchor_id,study_id,patient_id) REFERENCES event_revisions(id,study_id,patient_id),
 UNIQUE(study_id,patient_id,definition_version,content_hash)
);
CREATE INDEX memory_scope_time ON memory_episodes(study_id,patient_id,definition_version,available_at)
 WHERE NOT tombstoned;
-- Exact vector search within a bounded patient pool; no approximate global index.
CREATE TABLE memory_index_state (
 study_id uuid NOT NULL,
 patient_id uuid NOT NULL,
 definition_version text NOT NULL,
 watermark timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(study_id,patient_id,definition_version),
 FOREIGN KEY(patient_id,study_id) REFERENCES patients(id,study_id)
);
CREATE FUNCTION public.t1d_stamp_memory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 NEW.available_at=clock_timestamp();
 NEW.manifest=jsonb_set(NEW.manifest,'{available_at}',to_jsonb(NEW.available_at));
 RETURN NEW;
END $$;
CREATE TRIGGER stamp_memory BEFORE INSERT ON memory_episodes
 FOR EACH ROW EXECUTE FUNCTION public.t1d_stamp_memory();
CREATE FUNCTION public.t1d_memory_tombstone() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.tombstoned AND NOT NEW.tombstoned THEN
  RAISE EXCEPTION 'memory tombstones cannot be resurrected' USING ERRCODE='42501';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER irreversible_tombstone BEFORE UPDATE ON memory_episodes
 FOR EACH ROW EXECUTE FUNCTION public.t1d_memory_tombstone();
ALTER TABLE memory_episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_episodes FORCE ROW LEVEL SECURITY;
CREATE POLICY memory_scoped_read ON memory_episodes FOR SELECT
 USING(public.t1d_has_access(study_id,patient_id,false));
CREATE POLICY memory_scoped_insert ON memory_episodes FOR INSERT
 WITH CHECK(public.t1d_has_access(study_id,patient_id,true));
CREATE POLICY memory_scoped_update ON memory_episodes FOR UPDATE
 USING(public.t1d_has_access(study_id,patient_id,true))
 WITH CHECK(public.t1d_has_access(study_id,patient_id,true));
-- Runtime updates can only invalidate, never rewrite an episode or vector.
GRANT SELECT,INSERT ON memory_episodes TO t1d_runtime;
GRANT UPDATE(tombstoned) ON memory_episodes TO t1d_runtime;
ALTER TABLE memory_index_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_index_state FORCE ROW LEVEL SECURITY;
CREATE POLICY memory_state_scope ON memory_index_state
 USING(public.t1d_has_access(study_id,patient_id,false))
 WITH CHECK(public.t1d_has_access(study_id,patient_id,true));
GRANT SELECT,INSERT,UPDATE ON memory_index_state TO t1d_runtime;
