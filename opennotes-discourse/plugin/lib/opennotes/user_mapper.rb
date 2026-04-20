# frozen_string_literal: true

module OpenNotes
  class UserMapper
    CACHE_DURATION = 15 * 60

    def initialize(client)
      @client = client
      @cache = {}
    end

    def lookup_or_create(discourse_user)
      cached = @cache[discourse_user.id]
      if cached && cached[:expires_at] > Time.now
        return cached[:profile]
      end

      profile = fetch_profile(discourse_user)
      if profile
        @cache[discourse_user.id] = {
          profile: profile,
          expires_at: Time.now + CACHE_DURATION,
        }
      end
      profile
    end

    private

    def fetch_profile(discourse_user)
      @client.get(
        "#{OpenNotes::PUBLIC_API_PREFIX}/user-profiles/lookup",
        params: {
          platform: "discourse",
          platform_user_id: discourse_user.id.to_s,
          provider_scope: SiteSetting.opennotes_platform_community_server_id,
        },
        user: discourse_user,
      )
    rescue OpenNotes::ApiError => e
      return nil if e.status == 404
      raise
    end
  end
end
