-- Frozen initial table/index definitions; do not regenerate after application.

CREATE TABLE model_versions (
	model_name VARCHAR(128) NOT NULL,
	version VARCHAR(128) NOT NULL,
	artifact_object_ref VARCHAR(256) NOT NULL,
	artifact_digest VARCHAR(128) NOT NULL,
	code_revision VARCHAR(128) NOT NULL,
	data_manifest_ref VARCHAR(256) NOT NULL,
	feature_schema_version VARCHAR(128) NOT NULL,
	preprocessing_version VARCHAR(128) NOT NULL,
	evaluation_report_ref VARCHAR(256) NOT NULL,
	uncertainty_method VARCHAR(128) NOT NULL,
	status VARCHAR(32) NOT NULL,
	applicability JSONB NOT NULL,
	provenance JSONB NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (model_name, version),
	CHECK (status='candidate')
)

;

CREATE TABLE research_studies (
	reference VARCHAR(128) NOT NULL,
	active BOOLEAN NOT NULL,
	synthetic BOOLEAN NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (reference)
)

;

CREATE TABLE audit_events (
	study_id UUID,
	patient_id UUID,
	actor_ref VARCHAR(128) NOT NULL,
	action VARCHAR(64) NOT NULL,
	resource_type VARCHAR(32) NOT NULL,
	resource_id UUID,
	resource_revision INTEGER,
	source_ref VARCHAR(128),
	outcome VARCHAR(32) NOT NULL,
	reason_code VARCHAR(64),
	correlation_id UUID NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(study_id) REFERENCES research_studies (id)
)

;
CREATE INDEX ix_audit_scope_time ON audit_events (study_id, patient_id, created_at, id);

CREATE TABLE data_sources (
	study_id UUID NOT NULL,
	source_ref VARCHAR(128) NOT NULL,
	source_version VARCHAR(128) NOT NULL,
	source_type VARCHAR(16) NOT NULL,
	approved BOOLEAN NOT NULL,
	license_reference VARCHAR(256) NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (study_id, source_ref, source_version),
	FOREIGN KEY(study_id) REFERENCES research_studies (id)
)

;

CREATE TABLE patients (
	study_id UUID NOT NULL,
	research_subject_ref VARCHAR(128) NOT NULL,
	status VARCHAR(16) NOT NULL,
	provenance JSONB NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (id, study_id),
	UNIQUE (study_id, research_subject_ref),
	CHECK (status IN ('active','withdrawn','suspended')),
	FOREIGN KEY(study_id) REFERENCES research_studies (id)
)

;

CREATE TABLE access_grants (
	patient_id UUID NOT NULL,
	study_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	can_read BOOLEAN NOT NULL,
	can_write BOOLEAN NOT NULL,
	revoked BOOLEAN NOT NULL,
	valid_until TIMESTAMP WITH TIME ZONE NOT NULL,
	approved_by UUID NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(patient_id, study_id) REFERENCES patients (id, study_id),
	UNIQUE (study_id, patient_id, actor_id),
	CHECK (NOT can_write OR can_read)
)

;
CREATE INDEX ix_access_grants_actor_id ON access_grants (actor_id);

CREATE TABLE consent_records (
	patient_id UUID NOT NULL,
	study_id UUID NOT NULL,
	version INTEGER NOT NULL,
	status VARCHAR(16) NOT NULL,
	effective_at TIMESTAMP WITH TIME ZONE NOT NULL,
	valid_until TIMESTAMP WITH TIME ZONE,
	actor_id UUID NOT NULL,
	synthetic BOOLEAN NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(patient_id, study_id) REFERENCES patients (id, study_id),
	UNIQUE (study_id, patient_id, version),
	CHECK (status IN ('granted','revoked') AND version > 0),
	CHECK (valid_until IS NULL OR valid_until > effective_at)
)

;

CREATE TABLE event_revisions (
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	kind VARCHAR(16) NOT NULL,
	source_ref VARCHAR(128) NOT NULL,
	source_version VARCHAR(128) NOT NULL,
	source_event_ref VARCHAR(128) NOT NULL,
	stream_ref VARCHAR(128) NOT NULL,
	revision INTEGER NOT NULL,
	supersedes_id UUID,
	event_time TIMESTAMP WITH TIME ZONE NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ingested_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	original_offset VARCHAR(32) NOT NULL,
	provenance JSONB NOT NULL,
	content_digest VARCHAR(64) NOT NULL,
	quality_state VARCHAR(16) NOT NULL,
	quality_flags JSONB NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(patient_id, study_id) REFERENCES patients (id, study_id),
	FOREIGN KEY(study_id, source_ref, source_version) REFERENCES data_sources (study_id, source_ref, source_version),
	UNIQUE (id, study_id, patient_id),
	UNIQUE (id, study_id, patient_id, kind),
	UNIQUE (id, event_time, study_id, patient_id, kind),
	UNIQUE (id, event_time, study_id, patient_id),
	FOREIGN KEY(supersedes_id, study_id, patient_id) REFERENCES event_revisions (id, study_id, patient_id),
	UNIQUE (study_id, patient_id, kind, source_ref, stream_ref, source_event_ref, revision),
	CHECK (kind IN ('cgm','meal','insulin','activity')),
	CHECK (revision > 0 AND ((revision = 1 AND supersedes_id IS NULL) OR (revision > 1 AND supersedes_id IS NOT NULL))),
	CHECK (isfinite(event_time) AND isfinite(recorded_at) AND event_time <= ingested_at AND recorded_at <= ingested_at AND available_at >= ingested_at AND available_at >= recorded_at),
	CHECK (quality_state IN ('accepted','warning','quarantined')),
	UNIQUE (supersedes_id)
)

;
CREATE INDEX ix_events_scope_time ON event_revisions (study_id, patient_id, kind, event_time, available_at, id);

CREATE TABLE ingestion_batches (
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	operation VARCHAR(16) NOT NULL,
	key_digest VARCHAR(64) NOT NULL,
	request_digest VARCHAR(64) NOT NULL,
	response JSONB NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(patient_id, study_id) REFERENCES patients (id, study_id),
	UNIQUE (study_id, patient_id, actor_id, operation, key_digest)
)

;

CREATE TABLE activity_events (
	kind VARCHAR(16) DEFAULT 'activity' NOT NULL,
	activity_type VARCHAR(128) NOT NULL,
	start_at TIMESTAMP WITH TIME ZONE NOT NULL,
	end_at TIMESTAMP WITH TIME ZONE NOT NULL,
	duration_minutes NUMERIC NOT NULL,
	intensity_status VARCHAR(16) NOT NULL,
	intensity_value NUMERIC,
	intensity_unit VARCHAR(128),
	id UUID NOT NULL,
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	PRIMARY KEY (id),
	CHECK (kind='activity'),
	FOREIGN KEY(id, study_id, patient_id, kind) REFERENCES event_revisions (id, study_id, patient_id, kind),
	CHECK (end_at>=start_at AND duration_minutes>=0),
	CHECK ((intensity_status='unknown' AND intensity_value IS NULL AND intensity_unit IS NULL) OR (intensity_status='known' AND intensity_value IS NOT NULL AND intensity_value>=0 AND intensity_value<'Infinity'::numeric AND intensity_unit IS NOT NULL))
)

;

CREATE TABLE cgm_readings (
	kind VARCHAR(16) DEFAULT 'cgm' NOT NULL,
	event_time TIMESTAMP WITH TIME ZONE NOT NULL,
	glucose_value NUMERIC,
	glucose_unit VARCHAR(8) NOT NULL,
	glucose_mmol_l NUMERIC,
	conversion_version VARCHAR(32) NOT NULL,
	device_ref VARCHAR(128) NOT NULL,
	sensor_status VARCHAR(16) NOT NULL,
	id UUID NOT NULL,
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	PRIMARY KEY (event_time, id),
	CHECK (kind='cgm'),
	FOREIGN KEY(id, event_time, study_id, patient_id, kind) REFERENCES event_revisions (id, event_time, study_id, patient_id, kind),
	CHECK (glucose_unit IN ('mg/dL','mmol/L')),
	CHECK ((glucose_value IS NULL AND glucose_mmol_l IS NULL AND sensor_status='missing') OR (glucose_value IS NOT NULL AND glucose_mmol_l IS NOT NULL AND glucose_value>0 AND glucose_value<'Infinity'::numeric AND glucose_mmol_l>0 AND glucose_mmol_l<'Infinity'::numeric AND sensor_status IN ('valid','unverified')))
)

;
CREATE INDEX ix_cgm_scope_time ON cgm_readings (study_id, patient_id, event_time);

CREATE TABLE insulin_events (
	kind VARCHAR(16) DEFAULT 'insulin' NOT NULL,
	event_kind VARCHAR(32) NOT NULL,
	amount_value NUMERIC NOT NULL,
	amount_unit VARCHAR(8) NOT NULL,
	insulin_type_ref VARCHAR(128) NOT NULL,
	delivery_start TIMESTAMP WITH TIME ZONE,
	delivery_end TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	PRIMARY KEY (id),
	CHECK (kind='insulin'),
	FOREIGN KEY(id, study_id, patient_id, kind) REFERENCES event_revisions (id, study_id, patient_id, kind),
	CHECK (event_kind IN ('reported_delivery','planned','cancelled','corrected')),
	CHECK (amount_value>=0 AND amount_value<'Infinity'::numeric AND amount_unit='U'),
	CHECK (delivery_start IS NULL OR delivery_end IS NULL OR delivery_end>=delivery_start)
)

;

CREATE TABLE meals (
	kind VARCHAR(16) DEFAULT 'meal' NOT NULL,
	status VARCHAR(16) NOT NULL,
	meal_revision INTEGER NOT NULL,
	confirmed_by UUID,
	confirmed_at TIMESTAMP WITH TIME ZONE,
	id UUID NOT NULL,
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	PRIMARY KEY (id),
	CHECK (kind='meal'),
	FOREIGN KEY(id, study_id, patient_id, kind) REFERENCES event_revisions (id, study_id, patient_id, kind),
	UNIQUE (id, study_id, patient_id),
	CHECK ((status='draft' AND confirmed_by IS NULL AND confirmed_at IS NULL) OR (status='confirmed' AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL))
)

;

CREATE TABLE outbox_events (
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	event_revision_id UUID NOT NULL,
	operation VARCHAR(32) NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(event_revision_id, study_id, patient_id) REFERENCES event_revisions (id, study_id, patient_id)
)

;

CREATE TABLE meal_components (
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	meal_id UUID NOT NULL,
	meal_revision INTEGER NOT NULL,
	food_label VARCHAR(128) NOT NULL,
	status VARCHAR(16) NOT NULL,
	portion_value NUMERIC,
	portion_unit VARCHAR(8),
	food_reference_id VARCHAR(128),
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(meal_id, study_id, patient_id) REFERENCES meals (id, study_id, patient_id),
	UNIQUE (id, meal_id, study_id, patient_id),
	CHECK ((portion_value IS NULL AND portion_unit IS NULL) OR (portion_value IS NOT NULL AND portion_value>0 AND portion_value<'Infinity'::numeric AND portion_unit='g')),
	CHECK (status IN ('proposed','corrected','confirmed'))
)

;

CREATE TABLE nutrition_records (
	study_id UUID NOT NULL,
	patient_id UUID NOT NULL,
	meal_id UUID NOT NULL,
	meal_revision INTEGER NOT NULL,
	component_id UUID,
	scope VARCHAR(16) NOT NULL,
	carbohydrate_g NUMERIC NOT NULL,
	protein_g NUMERIC NOT NULL,
	fat_g NUMERIC NOT NULL,
	energy_kcal NUMERIC NOT NULL,
	reference_manifest JSONB NOT NULL,
	method_version VARCHAR(128) NOT NULL,
	uncertainty JSONB NOT NULL,
	available_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	id UUID DEFAULT gen_random_uuid() NOT NULL,
	schema_version INTEGER DEFAULT '1' NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(meal_id, study_id, patient_id) REFERENCES meals (id, study_id, patient_id),
	FOREIGN KEY(component_id, meal_id, study_id, patient_id) REFERENCES meal_components (id, meal_id, study_id, patient_id),
	CHECK ((scope='meal_total' AND component_id IS NULL) OR (scope='component' AND component_id IS NOT NULL)),
	CHECK (carbohydrate_g>=0 AND carbohydrate_g<'Infinity'::numeric),
	CHECK (protein_g>=0 AND protein_g<'Infinity'::numeric),
	CHECK (fat_g>=0 AND fat_g<'Infinity'::numeric),
	CHECK (energy_kcal>=0 AND energy_kcal<'Infinity'::numeric),
	UNIQUE (component_id)
)

;
CREATE UNIQUE INDEX uq_nutrition_total ON nutrition_records (meal_id) WHERE scope='meal_total';
