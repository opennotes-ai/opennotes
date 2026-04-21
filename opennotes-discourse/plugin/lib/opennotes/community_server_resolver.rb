# frozen_string_literal: true

module OpenNotes
  module CommunityServerResolver
    CACHE_KEY = "opennotes_community_server_uuid"
    CACHE_TTL = 5.minutes
    PLUGIN_NAMESPACE = "discourse-opennotes"
    PLUGIN_STORE_KEY = "community_server_uuid"

    module_function

    def community_server_uuid
      cached = Discourse.cache.read(CACHE_KEY)
      return cached if cached.present?

      stored = ::PluginStore.get(PLUGIN_NAMESPACE, PLUGIN_STORE_KEY)
      if stored.present?
        Discourse.cache.write(CACHE_KEY, stored, expires_in: CACHE_TTL)
        return stored
      end

      resolved = lookup_from_api
      return nil if resolved.blank?

      persist(resolved)
      resolved
    end

    def invalidate!
      Discourse.cache.delete(CACHE_KEY)
      ::PluginStore.remove(PLUGIN_NAMESPACE, PLUGIN_STORE_KEY)
    end

    def persist(uuid)
      ::PluginStore.set(PLUGIN_NAMESPACE, PLUGIN_STORE_KEY, uuid)
      Discourse.cache.write(CACHE_KEY, uuid, expires_in: CACHE_TTL)
    end

    def lookup_from_api
      server_url = SiteSetting.opennotes_server_url
      api_key = SiteSetting.opennotes_api_key
      slug = SiteSetting.opennotes_platform_community_server_id

      missing = []
      missing << "opennotes_server_url" if server_url.blank?
      missing << "opennotes_api_key" if api_key.blank?
      missing << "opennotes_platform_community_server_id" if slug.blank?
      if missing.any?
        Rails.logger.warn(
          "[OpenNotes] Cannot resolve community_server_uuid: missing #{missing.join(", ")}"
        )
        return nil
      end

      client = OpenNotes::Client.new(server_url: server_url, api_key: api_key)
      response = client.get(
        "#{OpenNotes::PUBLIC_API_PREFIX}/community-servers/lookup",
        params: { platform: "discourse", platform_community_server_id: slug },
      )
      extract_id(response)
    rescue OpenNotes::ApiError => e
      Rails.logger.warn("[OpenNotes] Community server lookup failed (status #{e.status}): #{e.body}")
      nil
    rescue Faraday::Error => e
      Rails.logger.warn("[OpenNotes] Community server lookup failed: #{e.class}: #{e.message}")
      nil
    end

    def extract_id(response)
      return nil unless response.is_a?(Hash)
      response["id"] || response[:id] ||
        response.dig("data", "id") || response.dig(:data, :id)
    end
  end
end
