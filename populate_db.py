from __future__ import annotations

import argparse
import importlib
import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_DSN = os.getenv("PG_DSN", "")


# Based on GDELT 2.0 Codebook (GDELT-Event_Codebook-V2.0.pdf)
QUAD_CLASS_CODES = [
	(1, "Verbal Cooperation", "Cooperative actions expressed verbally."),
	(2, "Material Cooperation", "Cooperative actions with material effects."),
	(3, "Verbal Conflict", "Conflictual actions expressed verbally."),
	(4, "Material Conflict", "Conflictual actions with material effects."),
]


# Based on Actor/Action Geo_Type definitions in the GDELT 2.0 codebook.
GEO_TYPE_CODES = [
	(1, "COUNTRY", "Country-level match."),
	(2, "USSTATE", "US state-level match."),
	(3, "USCITY", "US city/landmark-level match."),
	(4, "WORLDCITY", "Non-US city/landmark-level match."),
	(5, "WORLDSTATE", "Non-US ADM1/state-level match."),
]


# CAMEO root event classes used by GDELT EventRootCode.
# The GDELT codebook explains EventRootCode as the top-level class.
CAMEO_ROOT_EVENT_CODES = [
	("01", "Make Public Statement"),
	("02", "Appeal"),
	("03", "Express Intent to Cooperate"),
	("04", "Consult"),
	("05", "Engage in Diplomatic Cooperation"),
	("06", "Engage in Material Cooperation"),
	("07", "Provide Aid"),
	("08", "Yield"),
	("09", "Investigate"),
	("10", "Demand"),
	("11", "Disapprove"),
	("12", "Reject"),
	("13", "Threaten"),
	("14", "Protest"),
	("15", "Exhibit Military Posture"),
	("16", "Reduce Relations"),
	("17", "Coerce"),
	("18", "Assault"),
	("19", "Fight"),
	("20", "Engage in Unconventional Mass Violence"),
]


CODED_COLUMNS = [
	(
		"quadclass",
		"gdelt_dim_quad_class",
		"Primary CAMEO quad class: 1=Verbal Cooperation, 2=Material Cooperation, 3=Verbal Conflict, 4=Material Conflict.",
	),
	(
		"eventrootcode",
		"gdelt_dim_cameo_root_event",
		"Root CAMEO event category (2-digit code).",
	),
	(
		"actor1geo_type",
		"gdelt_dim_geo_type",
		"Geo resolution for Actor1 location.",
	),
	(
		"actor2geo_type",
		"gdelt_dim_geo_type",
		"Geo resolution for Actor2 location.",
	),
	(
		"actiongeo_type",
		"gdelt_dim_geo_type",
		"Geo resolution for Action location.",
	),
	(
		"eventcode",
		None,
		"Raw CAMEO action code (full hierarchy). Use external CAMEO crosswalk for exhaustive mapping.",
	),
	(
		"eventbasecode",
		None,
		"Level-2 CAMEO action code. Use external CAMEO crosswalk for exhaustive mapping.",
	),
	(
		"actor1countrycode",
		None,
		"3-character CAMEO country code for Actor1.",
	),
	(
		"actor2countrycode",
		None,
		"3-character CAMEO country code for Actor2.",
	),
	(
		"actor1knowngroupcode",
		None,
		"CAMEO known group code for Actor1 when applicable.",
	),
	(
		"actor2knowngroupcode",
		None,
		"CAMEO known group code for Actor2 when applicable.",
	),
	(
		"actor1ethniccode",
		None,
		"CAMEO ethnic code for Actor1 when applicable.",
	),
	(
		"actor2ethniccode",
		None,
		"CAMEO ethnic code for Actor2 when applicable.",
	),
	(
		"actor1religion1code",
		None,
		"Primary CAMEO religion code for Actor1 when applicable.",
	),
	(
		"actor1religion2code",
		None,
		"Secondary CAMEO religion code for Actor1 when applicable.",
	),
	(
		"actor2religion1code",
		None,
		"Primary CAMEO religion code for Actor2 when applicable.",
	),
	(
		"actor2religion2code",
		None,
		"Secondary CAMEO religion code for Actor2 when applicable.",
	),
	(
		"actor1type1code",
		None,
		"Primary CAMEO actor role/type code for Actor1.",
	),
	(
		"actor1type2code",
		None,
		"Secondary CAMEO actor role/type code for Actor1.",
	),
	(
		"actor1type3code",
		None,
		"Tertiary CAMEO actor role/type code for Actor1.",
	),
	(
		"actor2type1code",
		None,
		"Primary CAMEO actor role/type code for Actor2.",
	),
	(
		"actor2type2code",
		None,
		"Secondary CAMEO actor role/type code for Actor2.",
	),
	(
		"actor2type3code",
		None,
		"Tertiary CAMEO actor role/type code for Actor2.",
	),
]


def create_lookup_tables(conn) -> None:
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS gdelt_dim_quad_class (
			code INTEGER PRIMARY KEY,
			label TEXT NOT NULL,
			description TEXT
		)
		"""
	)
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS gdelt_dim_geo_type (
			code INTEGER PRIMARY KEY,
			label TEXT NOT NULL,
			description TEXT
		)
		"""
	)
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS gdelt_dim_cameo_root_event (
			code TEXT PRIMARY KEY,
			label TEXT NOT NULL
		)
		"""
	)
	conn.execute(
		"""
		CREATE TABLE IF NOT EXISTS gdelt_dim_coded_column_dictionary (
			column_name TEXT PRIMARY KEY,
			reference_table TEXT,
			description TEXT NOT NULL,
			source TEXT NOT NULL
		)
		"""
	)


def upsert_lookup_values(conn) -> None:
	with conn.cursor() as cur:
		cur.executemany(
			"""
			INSERT INTO gdelt_dim_quad_class (code, label, description)
			VALUES (%s, %s, %s)
			ON CONFLICT (code)
			DO UPDATE SET
				label = EXCLUDED.label,
				description = EXCLUDED.description
			""",
			QUAD_CLASS_CODES,
		)

		cur.executemany(
			"""
			INSERT INTO gdelt_dim_geo_type (code, label, description)
			VALUES (%s, %s, %s)
			ON CONFLICT (code)
			DO UPDATE SET
				label = EXCLUDED.label,
				description = EXCLUDED.description
			""",
			GEO_TYPE_CODES,
		)

		cur.executemany(
			"""
			INSERT INTO gdelt_dim_cameo_root_event (code, label)
			VALUES (%s, %s)
			ON CONFLICT (code)
			DO UPDATE SET
				label = EXCLUDED.label
			""",
			CAMEO_ROOT_EVENT_CODES,
		)

		coded_rows = [
			(column_name, ref_table, description, "GDELT-Event_Codebook-V2.0.pdf")
			for column_name, ref_table, description in CODED_COLUMNS
		]
		cur.executemany(
			"""
			INSERT INTO gdelt_dim_coded_column_dictionary (
				column_name,
				reference_table,
				description,
				source
			)
			VALUES (%s, %s, %s, %s)
			ON CONFLICT (column_name)
			DO UPDATE SET
				reference_table = EXCLUDED.reference_table,
				description = EXCLUDED.description,
				source = EXCLUDED.source
			""",
			coded_rows,
		)


def create_enriched_view(conn) -> None:
	conn.execute(
		"""
		CREATE OR REPLACE VIEW gdelt_brazil_events_enriched AS
		SELECT
			e.*,
			q.label AS quadclass_label,
			q.description AS quadclass_description,
			r.label AS eventrootcode_label,
			g1.label AS actor1geo_type_label,
			g2.label AS actor2geo_type_label,
			g3.label AS actiongeo_type_label
		FROM gdelt_brazil_events e
		LEFT JOIN gdelt_dim_quad_class q ON e.quadclass = q.code
		LEFT JOIN gdelt_dim_cameo_root_event r ON e.eventrootcode = r.code
		LEFT JOIN gdelt_dim_geo_type g1 ON e.actor1geo_type = g1.code
		LEFT JOIN gdelt_dim_geo_type g2 ON e.actor2geo_type = g2.code
		LEFT JOIN gdelt_dim_geo_type g3 ON e.actiongeo_type = g3.code
		"""
	)


def apply_foreign_keys(conn) -> None:
	conn.execute(
		"""
		DO $$
		BEGIN
			IF NOT EXISTS (
				SELECT 1
				FROM pg_constraint
				WHERE conname = 'fk_gdelt_events_quadclass'
			) THEN
				ALTER TABLE gdelt_brazil_events
					ADD CONSTRAINT fk_gdelt_events_quadclass
					FOREIGN KEY (quadclass)
					REFERENCES gdelt_dim_quad_class(code)
					NOT VALID;
			END IF;

			IF NOT EXISTS (
				SELECT 1
				FROM pg_constraint
				WHERE conname = 'fk_gdelt_events_eventrootcode'
			) THEN
				ALTER TABLE gdelt_brazil_events
					ADD CONSTRAINT fk_gdelt_events_eventrootcode
					FOREIGN KEY (eventrootcode)
					REFERENCES gdelt_dim_cameo_root_event(code)
					NOT VALID;
			END IF;

			IF NOT EXISTS (
				SELECT 1
				FROM pg_constraint
				WHERE conname = 'fk_gdelt_events_actor1geo_type'
			) THEN
				ALTER TABLE gdelt_brazil_events
					ADD CONSTRAINT fk_gdelt_events_actor1geo_type
					FOREIGN KEY (actor1geo_type)
					REFERENCES gdelt_dim_geo_type(code)
					NOT VALID;
			END IF;

			IF NOT EXISTS (
				SELECT 1
				FROM pg_constraint
				WHERE conname = 'fk_gdelt_events_actor2geo_type'
			) THEN
				ALTER TABLE gdelt_brazil_events
					ADD CONSTRAINT fk_gdelt_events_actor2geo_type
					FOREIGN KEY (actor2geo_type)
					REFERENCES gdelt_dim_geo_type(code)
					NOT VALID;
			END IF;

			IF NOT EXISTS (
				SELECT 1
				FROM pg_constraint
				WHERE conname = 'fk_gdelt_events_actiongeo_type'
			) THEN
				ALTER TABLE gdelt_brazil_events
					ADD CONSTRAINT fk_gdelt_events_actiongeo_type
					FOREIGN KEY (actiongeo_type)
					REFERENCES gdelt_dim_geo_type(code)
					NOT VALID;
			END IF;
		END $$;
		"""
	)


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description=(
			"Populate PostgreSQL lookup tables for coded GDELT 2.0 Event fields "
			"using the local GDELT codebook as reference."
		)
	)
	parser.add_argument(
		"--db-dsn",
		default=DEFAULT_DB_DSN,
		help=(
			"PostgreSQL DSN, e.g. "
			"postgresql://user:password@host:5432/database "
			"(or set PG_DSN env var)."
		),
	)
	parser.add_argument(
		"--apply-foreign-keys",
		action="store_true",
		help=(
			"Also add NOT VALID foreign keys from gdelt_brazil_events to the "
			"lookup tables for coded fields."
		),
	)
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	if not args.db_dsn:
		raise SystemExit("Missing PostgreSQL DSN. Pass --db-dsn or set PG_DSN.")

	psycopg = importlib.import_module("psycopg")
	with psycopg.connect(args.db_dsn) as conn:
		create_lookup_tables(conn)
		upsert_lookup_values(conn)
		create_enriched_view(conn)
		if args.apply_foreign_keys:
			apply_foreign_keys(conn)
		conn.commit()

	print("GDELT lookup tables populated successfully.")


if __name__ == "__main__":
	main()
