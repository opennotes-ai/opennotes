# frozen_string_literal: true

module OpenNotes
  module PlatformRegistrar
    REGISTRATION_SETTINGS = %w[
      opennotes_server_url
      opennotes_api_key
      opennotes_platform_community_server_id
    ].freeze

    module_function

    def register
      server_url = SiteSetting.opennotes_server_url
      api_key = SiteSetting.opennotes_api_key
      slug = SiteSetting.opennotes_platform_community_server_id

      if server_url.blank? || api_key.blank?
        return { ok: false, reason: :missing_settings, message: "opennotes_server_url or opennotes_api_key is blank" }
      end
      if slug.blank?
        return { ok: false, reason: :missing_settings, message: "opennotes_platform_community_server_id is blank" }
      end

      uuid = OpenNotes::CommunityServerResolver.community_server_id
      if uuid.blank?
        return { ok: false, reason: :lookup_failed, message: "Failed to resolve community server UUID" }
      end

      client = OpenNotes::Client.new(server_url: server_url, api_key: api_key)
      name = SiteSetting.title.to_s
      client.patch(
        "/api/v1/community-servers/#{slug}/name",
        params: { platform: "discourse" },
        body: {
          name: name,
          server_stats: { platform: "discourse", hostname: Discourse.current_hostname },
        },
      )
      { ok: true, uuid: uuid, name: name, slug: slug }
    rescue OpenNotes::ApiError => e
      Rails.logger.warn("[OpenNotes] Registration PATCH /name failed (#{e.status}): #{e.body}")
      { ok: false, reason: :api_error, message: e.message, status: e.status, body: e.body, uuid: uuid }
    rescue Faraday::Error => e
      Rails.logger.warn("[OpenNotes] Registration connection failed: #{e.class}: #{e.message}")
      { ok: false, reason: :connection_error, message: e.message, uuid: uuid }
    end

    def on_setting_saved(setting_name)
      return unless REGISTRATION_SETTINGS.include?(setting_name.to_s)

      if setting_name.to_s == "opennotes_platform_community_server_id"
        OpenNotes::CommunityServerResolver.invalidate!
      end

      result = register
      if result[:ok]
        Rails.logger.info("[OpenNotes] Registered community server uuid=#{result[:uuid]} name=#{result[:name]}")
      else
        Rails.logger.warn("[OpenNotes] Registration skipped or failed: #{result[:message]}")
      end
      result
    end
  end
end
