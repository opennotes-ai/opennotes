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

      client = OpenNotes::Client.new(server_url: server_url, api_key: api_key)
      name = SiteSetting.title.to_s

      uuid = OpenNotes::CommunityServerResolver.community_server_uuid
      if uuid.blank?
        created = create_community_server(client: client, slug: slug, name: name)
        case created[:status]
        when :created
          uuid = created[:uuid]
        when :conflict
          uuid = OpenNotes::CommunityServerResolver.community_server_uuid
          if uuid.blank?
            return {
              ok: false,
              reason: :lookup_failed,
              message: "Community server exists on server but lookup still returns nil",
            }
          end
        when :api_error
          return {
            ok: false,
            reason: :create_failed,
            message: created[:message],
            status: created[:status_code],
            body: created[:body],
          }
        when :connection_error
          return { ok: false, reason: :connection_error, message: created[:message] }
        else
          return { ok: false, reason: :lookup_failed, message: "Failed to resolve or create community server" }
        end
      end

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

    def create_community_server(client:, slug:, name:)
      body = {
        platform: "discourse",
        platform_community_server_id: slug,
        name: name.presence || slug,
      }
      response = client.post("/api/v1/community-servers", body: body)
      uuid = extract_created_uuid(response)
      if uuid.blank?
        return { status: :api_error, message: "Create response missing uuid", body: response }
      end
      OpenNotes::CommunityServerResolver.persist(uuid)
      { status: :created, uuid: uuid }
    rescue OpenNotes::ApiError => e
      if e.status == 409
        Rails.logger.info(
          "[OpenNotes] Community server already exists on server (409); re-resolving via lookup"
        )
        OpenNotes::CommunityServerResolver.invalidate!
        return { status: :conflict }
      end
      Rails.logger.warn("[OpenNotes] Community server create failed (#{e.status}): #{e.body}")
      { status: :api_error, message: e.message, status_code: e.status, body: e.body }
    rescue Faraday::Error => e
      Rails.logger.warn("[OpenNotes] Community server create connection failed: #{e.class}: #{e.message}")
      { status: :connection_error, message: e.message }
    end

    def extract_created_uuid(response)
      return nil unless response.is_a?(Hash)
      response["id"] || response[:id] ||
        response.dig("data", "id") || response.dig(:data, :id)
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
