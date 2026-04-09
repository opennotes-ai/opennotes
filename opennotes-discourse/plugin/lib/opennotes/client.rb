# frozen_string_literal: true

module OpenNotes
  class ApiError < StandardError
    attr_reader :status, :body

    def initialize(status, body)
      @status = status
      @body = body
      super("OpenNotes API error #{status}: #{body}")
    end
  end

  class Client
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 0.5
    RETRYABLE_STATUSES = [429, 500, 502, 503, 504].freeze

    attr_reader :server_url

    def initialize(server_url:, api_key:)
      @api_key = api_key
      @connection = Faraday.new(url: server_url) do |f|
        f.request :json
        f.response :json
        f.adapter Faraday.default_adapter
      end
      @server_url = server_url
    end

    def get(path, params: {}, user: nil)
      request_with_retries(:get, path, params: params, user: user)
    end

    def post(path, body: {}, user: nil)
      request_with_retries(:post, path, body: body, user: user)
    end

    def patch(path, body: {}, user: nil)
      request_with_retries(:patch, path, body: body, user: user)
    end

    def delete(path, user: nil)
      request_with_retries(:delete, path, user: user)
    end

    private

    def request_with_retries(method, path, params: nil, body: nil, user: nil)
      retries = 0

      loop do
        response = execute_request(method, path, params: params, body: body, user: user)

        if response.success?
          return response.body
        elsif RETRYABLE_STATUSES.include?(response.status) && retries < MAX_RETRIES
          retries += 1
          sleep(INITIAL_BACKOFF * (2**(retries - 1)))
        else
          raise ApiError.new(response.status, response.body)
        end
      end
    end

    def execute_request(method, path, params: nil, body: nil, user: nil)
      @connection.send(method, path) do |req|
        req.headers["Authorization"] = "Bearer #{@api_key}"
        req.headers["X-Platform-Type"] = "discourse"

        if user
          req.headers["X-Adapter-Platform"] = "discourse"
          req.headers["X-Adapter-User-Id"] = user.id.to_s
          req.headers["X-Adapter-Username"] = user.username
          req.headers["X-Adapter-Trust-Level"] = user.trust_level.to_s
          req.headers["X-Adapter-Admin"] = user.admin?.to_s
          req.headers["X-Adapter-Moderator"] = user.moderator?.to_s
          req.headers["X-Adapter-Scope"] = Discourse.current_hostname
        end

        req.params = params if params&.any?
        req.body = body if body
      end
    end
  end
end
