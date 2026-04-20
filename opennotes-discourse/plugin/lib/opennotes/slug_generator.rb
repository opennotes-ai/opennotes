# frozen_string_literal: true

require "digest"

module OpenNotes
  module SlugGenerator
    MAX_LENGTH = 255
    SUFFIX_LENGTH = 8

    module_function

    def generate(hostname:, contact_email:)
      host = hostname.to_s
      email = contact_email.to_s
      slug = if email.empty?
        host
      else
        suffix = Digest::SHA256.hexdigest(email)[0, SUFFIX_LENGTH]
        "#{host}-#{suffix}"
      end
      slug[0, MAX_LENGTH]
    end

    def generate_for_site
      hostname = Discourse.current_hostname
      contact_email = SiteSetting.contact_email
      if contact_email.to_s.empty?
        Rails.logger.warn(
          "[OpenNotes] contact_email blank; falling back to hostname-only platform_community_server_id"
        )
      end
      generate(hostname: hostname, contact_email: contact_email)
    end
  end
end
