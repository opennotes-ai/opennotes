import argparse
import importlib.util
import sys
from pathlib import Path

import yaml

_SCRIPTS_FIXTURES_DIR = Path(__file__).parent
_OPENNOTES_SERVER_DIR = _SCRIPTS_FIXTURES_DIR.parent.parent / "opennotes-server"

if str(_OPENNOTES_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_OPENNOTES_SERVER_DIR))


def _load_rules() -> dict:
    spec = importlib.util.spec_from_file_location(
        "_anonymization_rules",
        _SCRIPTS_FIXTURES_DIR / "anonymization_rules.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load anonymization_rules.py from {_SCRIPTS_FIXTURES_DIR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.RULES  # type: ignore[attr-defined]


def generate_config(tables: list[str] | None = None) -> dict:
    from src.database import Base

    import src.auth.models  # noqa: F401
    import src.batch_jobs.models  # noqa: F401
    import src.bulk_content_scan.models  # noqa: F401
    import src.community_config.models  # noqa: F401
    import src.fact_checking.candidate_models  # noqa: F401
    import src.fact_checking.chunk_models  # noqa: F401
    import src.fact_checking.dataset_models  # noqa: F401
    import src.fact_checking.models  # noqa: F401
    import src.fact_checking.monitored_channel_models  # noqa: F401
    import src.fact_checking.previously_seen_models  # noqa: F401
    import src.llm_config.models  # noqa: F401
    import src.moderation_actions.models  # noqa: F401
    import src.notes.message_archive_models  # noqa: F401
    import src.notes.models  # noqa: F401
    import src.notes.note_publisher_models  # noqa: F401
    import src.notes.scoring.models  # noqa: F401
    import src.users.models  # noqa: F401
    import src.users.profile_models  # noqa: F401
    import src.webhooks.delivery_models  # noqa: F401
    import src.webhooks.models  # noqa: F401

    rules = _load_rules()

    config: dict = {
        "common": {"pg_bin_path": "", "tmp_dir": "/tmp/greenmask"},
        "storage": {"type": "directory", "directory": {"path": "/tmp/greenmask-output"}},
        "dump": {
            "pg_dump_options": {
                "dbname": "${DATABASE_URL}",
                "jobs": 4,
                "schema": "public",
            },
            "transformation": [],
        },
    }

    for table in Base.metadata.sorted_tables:
        if tables and table.name not in tables:
            continue

        table_rules = {
            (t, c): rule for (t, c), rule in rules.items() if t == table.name
        }

        if not table_rules:
            continue

        transformers = []
        for (_, col_name), rule in table_rules.items():
            transformer: dict = {"name": rule["name"], "params": {"column": col_name}}
            if "params" in rule:
                transformer["params"].update(rule["params"])
            transformers.append(transformer)

        config["dump"]["transformation"].append({
            "schema": "public",
            "name": str(table.name),
            "transformers": transformers,
        })

    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate Greenmask anonymization config from SQLAlchemy models"
    )
    parser.add_argument("--tables", help="Comma-separated table names for partial export")
    parser.add_argument("--output", default="greenmask-config.yml")
    args = parser.parse_args()

    tables = args.tables.split(",") if args.tables else None
    config = generate_config(tables)

    with open(args.output, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print(f"Generated {args.output}")
