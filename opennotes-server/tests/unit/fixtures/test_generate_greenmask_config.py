from opennotes_scripts.fixtures.anonymization_rules import RULES
from opennotes_scripts.fixtures.generate_greenmask_config import generate_config


class TestGenerateConfig:
    def test_returns_valid_top_level_structure(self):
        config = generate_config()
        assert "common" in config
        assert "storage" in config
        assert "dump" in config
        assert "transformation" in config["dump"]
        assert isinstance(config["dump"]["transformation"], list)

    def test_transformation_entries_are_non_empty(self):
        config = generate_config()
        transformation = config["dump"]["transformation"]
        assert len(transformation) > 0

    def test_each_entry_has_required_fields(self):
        config = generate_config()
        for entry in config["dump"]["transformation"]:
            assert "schema" in entry
            assert entry["schema"] == "public"
            assert "name" in entry
            assert "transformers" in entry
            assert isinstance(entry["transformers"], list)
            assert len(entry["transformers"]) > 0

    def test_each_transformer_has_name_and_params_with_column(self):
        config = generate_config()
        for entry in config["dump"]["transformation"]:
            for transformer in entry["transformers"]:
                assert "name" in transformer
                assert "params" in transformer
                assert "column" in transformer["params"]

    def test_known_pii_tables_present(self):
        config = generate_config()
        table_names = {entry["name"] for entry in config["dump"]["transformation"]}
        expected_tables = {
            "users",
            "user_profiles",
            "user_identities",
            "refresh_tokens",
            "api_keys",
            "audit_logs",
            "message_archive",
            "monitored_channels",
            "webhooks",
            "interactions",
            "note_publisher_posts",
            "note_publisher_config",
            "community_server_llm_config",
            "previously_seen_messages",
        }
        for table in expected_tables:
            assert table in table_names, f"Expected table {table!r} in transformation config"

    def test_users_pii_columns_present(self):
        config = generate_config()
        users_entry = next(e for e in config["dump"]["transformation"] if e["name"] == "users")
        col_to_transformer = {t["params"]["column"]: t["name"] for t in users_entry["transformers"]}
        assert col_to_transformer["email"] == "RandomEmail"
        assert col_to_transformer["username"] == "RandomFirstName"
        assert col_to_transformer["hashed_password"] == "Hash"
        assert col_to_transformer["discord_id"] == "RandomInt"
        assert col_to_transformer["full_name"] == "RandomLastName"

    def test_audit_logs_pii_columns(self):
        config = generate_config()
        entry = next(e for e in config["dump"]["transformation"] if e["name"] == "audit_logs")
        col_to_transformer = {t["params"]["column"]: t["name"] for t in entry["transformers"]}
        assert col_to_transformer["ip_address"] == "RandomIPv4"
        assert col_to_transformer["user_agent"] == "RandomString"

    def test_api_keys_pii_columns(self):
        config = generate_config()
        entry = next(e for e in config["dump"]["transformation"] if e["name"] == "api_keys")
        col_to_transformer = {t["params"]["column"]: t["name"] for t in entry["transformers"]}
        assert col_to_transformer["key_hash"] == "Hash"
        assert col_to_transformer["name"] == "RandomString"

    def test_refresh_tokens_pii_columns(self):
        config = generate_config()
        entry = next(e for e in config["dump"]["transformation"] if e["name"] == "refresh_tokens")
        col_to_transformer = {t["params"]["column"]: t["name"] for t in entry["transformers"]}
        assert col_to_transformer["token"] == "Hash"
        assert col_to_transformer["token_hash"] == "Hash"

    def test_table_filter_limits_output(self):
        config = generate_config(tables=["users"])
        transformation = config["dump"]["transformation"]
        assert len(transformation) == 1
        assert transformation[0]["name"] == "users"

    def test_table_filter_multiple_tables(self):
        config = generate_config(tables=["users", "audit_logs"])
        transformation = config["dump"]["transformation"]
        table_names = {e["name"] for e in transformation}
        assert table_names == {"users", "audit_logs"}

    def test_table_filter_non_pii_table_produces_empty_config(self):
        config = generate_config(tables=["notes"])
        transformation = config["dump"]["transformation"]
        assert len(transformation) == 0

    def test_table_filter_unknown_table_produces_empty_config(self):
        config = generate_config(tables=["nonexistent_table"])
        transformation = config["dump"]["transformation"]
        assert len(transformation) == 0

    def test_non_pii_tables_not_in_transformation(self):
        config = generate_config()
        table_names = {entry["name"] for entry in config["dump"]["transformation"]}
        non_pii_tables = ["notes", "ratings", "requests", "scoring_snapshots", "batch_jobs"]
        for table in non_pii_tables:
            assert table not in table_names, (
                f"Non-PII table {table!r} should not appear in transformation config"
            )

    def test_hash_transformer_includes_algorithm(self):
        config = generate_config()
        users_entry = next(e for e in config["dump"]["transformation"] if e["name"] == "users")
        hash_transformer = next(
            t for t in users_entry["transformers"] if t["params"]["column"] == "hashed_password"
        )
        assert hash_transformer["name"] == "Hash"
        assert hash_transformer["params"]["algorithm"] == "sha256"

    def test_random_int_transformer_includes_min_max(self):
        config = generate_config()
        users_entry = next(e for e in config["dump"]["transformation"] if e["name"] == "users")
        discord_transformer = next(
            t for t in users_entry["transformers"] if t["params"]["column"] == "discord_id"
        )
        assert discord_transformer["name"] == "RandomInt"
        assert discord_transformer["params"]["min"] == 100000000000000000
        assert discord_transformer["params"]["max"] == 999999999999999999

    def test_database_url_placeholder_in_config(self):
        config = generate_config()
        dbname = config["dump"]["pg_dump_options"]["dbname"]
        assert dbname == "${DATABASE_URL}"

    def test_rules_dict_coverage(self):
        tables_in_rules = {table for table, _ in RULES}
        config = generate_config()
        table_names_in_config = {entry["name"] for entry in config["dump"]["transformation"]}
        for table in tables_in_rules:
            assert table in table_names_in_config, (
                f"Table {table!r} is in RULES but not found in metadata — "
                "check that the model is imported in generate_config()"
            )
