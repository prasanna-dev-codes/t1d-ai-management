SELECT create_hypertable('cgm_readings','event_time',chunk_time_interval=>INTERVAL '7 days',if_not_exists=>TRUE);

CREATE FUNCTION public.t1d_context_patient() RETURNS uuid LANGUAGE plpgsql STABLE SET search_path=pg_catalog AS $$
BEGIN
 RETURN nullif(current_setting('t1d.patient_id',true),'')::uuid;
EXCEPTION WHEN invalid_text_representation THEN RETURN NULL;
END $$;

CREATE FUNCTION public.t1d_has_access(s uuid,p uuid,w boolean) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT coalesce(
  s::text=current_setting('t1d.study_id',true) AND p::text=current_setting('t1d.patient_id',true)
  AND EXISTS (
   SELECT 1 FROM public.patients pt JOIN public.research_studies st ON st.id=pt.study_id
   JOIN public.access_grants g ON g.patient_id=pt.id AND g.study_id=pt.study_id
   WHERE pt.id=p AND pt.study_id=s AND pt.status='active' AND st.active
   AND g.actor_id::text=current_setting('t1d.actor_id',true) AND NOT g.revoked
   AND g.valid_until>clock_timestamp() AND g.can_read AND (NOT w OR g.can_write)
   AND EXISTS (
    SELECT 1 FROM (SELECT c.status,c.valid_until FROM public.consent_records c
     WHERE c.patient_id=p AND c.study_id=s AND c.effective_at<=clock_timestamp()
     ORDER BY c.version DESC LIMIT 1) latest
    WHERE latest.status='granted' AND (latest.valid_until IS NULL OR latest.valid_until>clock_timestamp())
   )
  ),false)
$$;
REVOKE ALL ON FUNCTION public.t1d_has_access(uuid,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.t1d_has_access(uuid,uuid,boolean) TO t1d_runtime;

CREATE FUNCTION public.t1d_authorize_and_lock(s uuid,p uuid,w boolean) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT public.t1d_has_access(s,p,w) THEN RETURN false; END IF;
 PERFORM id FROM public.patients WHERE id=p AND study_id=s FOR SHARE;
 RETURN public.t1d_has_access(s,p,w);
END $$;
REVOKE ALL ON FUNCTION public.t1d_authorize_and_lock(uuid,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.t1d_authorize_and_lock(uuid,uuid,boolean) TO t1d_runtime;

CREATE FUNCTION public.t1d_stamp_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior public.event_revisions%ROWTYPE;
BEGIN
 NEW.ingested_at=clock_timestamp(); NEW.created_at=NEW.ingested_at; NEW.available_at=NEW.ingested_at;
 IF NEW.revision>1 THEN
  SELECT * INTO prior FROM public.event_revisions WHERE id=NEW.supersedes_id;
  IF NOT FOUND OR (prior.study_id,prior.patient_id,prior.kind,prior.source_ref,prior.stream_ref,prior.source_event_ref,prior.revision+1)
       IS DISTINCT FROM (NEW.study_id,NEW.patient_id,NEW.kind,NEW.source_ref,NEW.stream_ref,NEW.source_event_ref,NEW.revision)
  THEN RAISE EXCEPTION 'invalid revision chain' USING ERRCODE='23514'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER stamp_revision BEFORE INSERT ON public.event_revisions FOR EACH ROW EXECUTE FUNCTION public.t1d_stamp_revision();

CREATE FUNCTION public.t1d_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'append-only record' USING ERRCODE='42501'; END $$;

CREATE FUNCTION public.t1d_control_lock() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 PERFORM id FROM public.patients WHERE id=NEW.patient_id AND study_id=NEW.study_id FOR UPDATE;
 RETURN NEW;
END $$;
CREATE TRIGGER control_lock BEFORE INSERT OR UPDATE ON public.consent_records FOR EACH ROW EXECUTE FUNCTION public.t1d_control_lock();
CREATE TRIGGER control_lock BEFORE INSERT OR UPDATE ON public.access_grants FOR EACH ROW EXECUTE FUNCTION public.t1d_control_lock();

CREATE FUNCTION public.t1d_control_audit() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE j jsonb;
BEGIN
 j=to_jsonb(NEW);
 INSERT INTO public.audit_events(study_id,patient_id,actor_ref,action,resource_type,resource_id,resource_revision,outcome,reason_code,correlation_id)
 VALUES(NEW.study_id,NEW.patient_id,coalesce(j->>'approved_by',j->>'actor_id'),'control_change',TG_TABLE_NAME,NEW.id,(j->>'version')::integer,'recorded','CONTROL_CHANGE',gen_random_uuid());
 RETURN NEW;
END $$;
CREATE TRIGGER control_audit AFTER INSERT OR UPDATE ON public.consent_records FOR EACH ROW EXECUTE FUNCTION public.t1d_control_audit();
CREATE TRIGGER control_audit AFTER INSERT OR UPDATE ON public.access_grants FOR EACH ROW EXECUTE FUNCTION public.t1d_control_audit();

CREATE FUNCTION public.t1d_record_failure(code text,op text,correlation uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF code NOT IN ('RESOURCE_UNAVAILABLE','INVALID_TIMESTAMP','SOURCE_UNAVAILABLE','EVENT_CONFLICT','IDEMPOTENCY_CONFLICT','DATABASE_UNAVAILABLE','DATABASE_CONFIGURATION','INVALID_INPUT','INVALID_UNIT','UNAUTHENTICATED','PAYLOAD_TOO_LARGE') OR op NOT IN ('cgm','meal','insulin','activity','history','validation','auth') THEN
  RAISE EXCEPTION 'unsupported audit category';
 END IF;
 INSERT INTO public.audit_events(actor_ref,action,resource_type,outcome,reason_code,correlation_id)
 VALUES(coalesce(nullif(current_setting('t1d.actor_id',true),''),'unauthenticated'),'rejected',op,'rejected',code,correlation);
END $$;
REVOKE ALL ON FUNCTION public.t1d_record_failure(text,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.t1d_record_failure(text,text,uuid) TO t1d_runtime;

GRANT USAGE ON SCHEMA public TO t1d_runtime;
GRANT SELECT ON alembic_version TO t1d_runtime;
GRANT SELECT ON research_studies,patients,consent_records,access_grants,data_sources TO t1d_runtime;
GRANT SELECT,INSERT ON event_revisions,cgm_readings,meals,meal_components,nutrition_records,insulin_events,activity_events,ingestion_batches,audit_events,outbox_events TO t1d_runtime;

ALTER TABLE event_revisions ENABLE ROW LEVEL SECURITY; ALTER TABLE event_revisions FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON event_revisions USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE cgm_readings ENABLE ROW LEVEL SECURITY; ALTER TABLE cgm_readings FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON cgm_readings USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE meals ENABLE ROW LEVEL SECURITY; ALTER TABLE meals FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON meals USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE meal_components ENABLE ROW LEVEL SECURITY; ALTER TABLE meal_components FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON meal_components USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE nutrition_records ENABLE ROW LEVEL SECURITY; ALTER TABLE nutrition_records FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON nutrition_records USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE insulin_events ENABLE ROW LEVEL SECURITY; ALTER TABLE insulin_events FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON insulin_events USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE activity_events ENABLE ROW LEVEL SECURITY; ALTER TABLE activity_events FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON activity_events USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE ingestion_batches ENABLE ROW LEVEL SECURITY; ALTER TABLE ingestion_batches FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON ingestion_batches USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE outbox_events ENABLE ROW LEVEL SECURITY; ALTER TABLE outbox_events FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_access ON outbox_events USING (public.t1d_has_access(study_id,patient_id,false)) WITH CHECK (public.t1d_has_access(study_id,patient_id,true));

ALTER TABLE patients ENABLE ROW LEVEL SECURITY; ALTER TABLE patients FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON patients FOR SELECT USING (public.t1d_has_access(study_id,id,false));

ALTER TABLE research_studies ENABLE ROW LEVEL SECURITY; ALTER TABLE research_studies FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON research_studies FOR SELECT USING (public.t1d_has_access(id,public.t1d_context_patient(),false));

ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY; ALTER TABLE consent_records FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON consent_records FOR SELECT USING (public.t1d_has_access(study_id,patient_id,false));

ALTER TABLE access_grants ENABLE ROW LEVEL SECURITY; ALTER TABLE access_grants FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON access_grants FOR SELECT USING (actor_id::text=current_setting('t1d.actor_id',true) AND public.t1d_has_access(study_id,patient_id,false));

ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY; ALTER TABLE data_sources FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON data_sources FOR SELECT USING (public.t1d_has_access(study_id,public.t1d_context_patient(),false));

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY; ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON audit_events FOR SELECT USING (public.t1d_has_access(study_id,patient_id,false));

ALTER TABLE model_versions ENABLE ROW LEVEL SECURITY; ALTER TABLE model_versions FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON model_versions FOR SELECT USING (false);
CREATE POLICY audit_append ON audit_events FOR INSERT WITH CHECK (actor_ref=current_setting('t1d.actor_id',true) AND public.t1d_has_access(study_id,patient_id,false));
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON event_revisions FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON cgm_readings FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON meals FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON meal_components FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON nutrition_records FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON insulin_events FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON activity_events FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON ingestion_batches FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON outbox_events FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON consent_records FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON model_versions FOR EACH ROW EXECUTE FUNCTION public.t1d_immutable();
