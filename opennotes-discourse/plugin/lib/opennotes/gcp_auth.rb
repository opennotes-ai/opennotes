# frozen_string_literal: true

require "base64"
require "cgi"
require "json"

module OpenNotes
  module GcpAuth
    METADATA_URL = "http://metadata.google.internal"
    METADATA_PATH = "/computeMetadata/v1/instance/service-accounts/default/identity"
    REFRESH_BUFFER_SECONDS = 60
    FALLBACK_EXPIRY_SECONDS = 55 * 60
    PROBE_TIMEOUT_SECONDS = 2
    FETCH_TIMEOUT_SECONDS = 5

    class << self
      def on_gcp?
        return @on_gcp unless @on_gcp.nil?
        @on_gcp = detect_gcp
      end

      def identity_token(audience)
        cached = token_cache[audience]
        if cached && Time.now.to_i < cached[:expires_at] - REFRESH_BUFFER_SECONDS
          return cached[:token]
        end

        token = fetch_identity_token(audience)
        return nil if token.nil? || token.empty?

        expires_at = parse_jwt_exp(token) || (Time.now.to_i + FALLBACK_EXPIRY_SECONDS)
        token_cache[audience] = { token: token, expires_at: expires_at }
        token
      end

      def reset_cache!
        @on_gcp = nil
        @token_cache = {}
      end

      def metadata_connection
        @metadata_connection ||= Faraday.new(url: METADATA_URL) do |f|
          f.headers["Metadata-Flavor"] = "Google"
          f.adapter Faraday.default_adapter
        end
      end

      private

      def token_cache
        @token_cache ||= {}
      end

      def detect_gcp
        return true if ENV["K_SERVICE"].to_s != ""
        probe_metadata_server
      end

      def probe_metadata_server
        response = metadata_connection.get("/") do |req|
          req.options.timeout = PROBE_TIMEOUT_SECONDS
          req.options.open_timeout = PROBE_TIMEOUT_SECONDS
        end
        response.success?
      rescue Faraday::Error
        false
      end

      def fetch_identity_token(audience)
        path = "#{METADATA_PATH}?audience=#{CGI.escape(audience)}"
        response = metadata_connection.get(path) do |req|
          req.options.timeout = FETCH_TIMEOUT_SECONDS
          req.options.open_timeout = PROBE_TIMEOUT_SECONDS
        end
        return nil unless response.success?
        response.body.to_s.strip
      rescue Faraday::Error => e
        Rails.logger.warn("[OpenNotes] Failed to fetch GCP identity token: #{e.class} #{e.message}") if defined?(Rails)
        nil
      end

      def parse_jwt_exp(token)
        parts = token.split(".")
        return nil unless parts.length == 3

        payload_json = Base64.urlsafe_decode64(pad_base64(parts[1]))
        payload = JSON.parse(payload_json)
        payload["exp"]&.to_i
      rescue StandardError
        nil
      end

      def pad_base64(str)
        pad = (4 - (str.length % 4)) % 4
        pad.zero? ? str : "#{str}#{'=' * pad}"
      end
    end
  end
end
