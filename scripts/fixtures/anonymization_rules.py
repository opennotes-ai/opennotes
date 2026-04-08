RULES: dict[tuple[str, str], dict] = {
    # users table
    ("users", "email"): {"name": "RandomEmail"},
    ("users", "username"): {"name": "RandomFirstName"},
    ("users", "hashed_password"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("users", "discord_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("users", "full_name"): {"name": "RandomLastName"},

    # user_profiles table
    ("user_profiles", "display_name"): {"name": "RandomFirstName"},
    ("user_profiles", "avatar_url"): {"name": "RandomURL"},
    ("user_profiles", "bio"): {"name": "RandomString", "params": {"min_length": 10, "max_length": 100}},
    ("user_profiles", "banned_reason"): {"name": "SetNull"},

    # user_identities table
    ("user_identities", "provider_user_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("user_identities", "credentials"): {"name": "SetNull"},
    ("user_identities", "email_verification_token"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # refresh_tokens table
    ("refresh_tokens", "token"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("refresh_tokens", "token_hash"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # api_keys table
    ("api_keys", "key_hash"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("api_keys", "name"): {"name": "RandomString", "params": {"min_length": 5, "max_length": 20}},

    # audit_logs table
    ("audit_logs", "ip_address"): {"name": "RandomIPv4"},
    ("audit_logs", "user_agent"): {"name": "RandomString", "params": {"min_length": 10, "max_length": 50}},
    ("audit_logs", "details"): {"name": "SetNull"},

    # message_archive table
    ("message_archive", "platform_author_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("message_archive", "platform_message_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("message_archive", "platform_channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("message_archive", "content_text"): {"name": "RandomString", "params": {"min_length": 10, "max_length": 200}},

    # monitored_channels table
    ("monitored_channels", "channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("monitored_channels", "updated_by"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # webhooks table
    ("webhooks", "url"): {"name": "RandomURL"},
    ("webhooks", "secret"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("webhooks", "channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # interactions table
    ("interactions", "user_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("interactions", "channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("interactions", "data"): {"name": "SetNull"},

    # note_publisher_posts table
    ("note_publisher_posts", "original_message_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("note_publisher_posts", "channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # note_publisher_config table
    ("note_publisher_config", "channel_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("note_publisher_config", "updated_by"): {"name": "Hash", "params": {"algorithm": "sha256"}},

    # community_server_llm_config table
    ("community_server_llm_config", "api_key_encrypted"): {"name": "Hash", "params": {"algorithm": "sha256"}},
    ("community_server_llm_config", "api_key_preview"): {"name": "RandomString", "params": {"min_length": 4, "max_length": 4}},

    # community_members table
    ("community_members", "banned_reason"): {"name": "SetNull"},
    ("community_members", "invitation_reason"): {"name": "SetNull"},

    # previously_seen_messages table
    ("previously_seen_messages", "original_message_id"): {"name": "Hash", "params": {"algorithm": "sha256"}},
}
