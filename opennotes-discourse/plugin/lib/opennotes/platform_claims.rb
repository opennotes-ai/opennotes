# frozen_string_literal: true

module OpenNotes
  module PlatformClaims
    ALGORITHM = "HS256"
    TOKEN_LIFETIME = 3600

    def self.claims_for(user)
      {
        platform: "discourse",
        scope: Discourse.current_hostname,
        sub: user.id.to_s,
        username: user.username,
        trust_level: user.trust_level,
        admin: user.admin?,
        moderator: user.moderator?,
      }
    end

    def self.sign(user:, scope: nil, secret:)
      payload = claims_for(user)
      payload[:scope] = scope if scope
      now = Time.now.to_i
      payload[:iat] = now
      payload[:exp] = now + TOKEN_LIFETIME
      JWT.encode(payload, secret, ALGORITHM)
    end
  end
end
