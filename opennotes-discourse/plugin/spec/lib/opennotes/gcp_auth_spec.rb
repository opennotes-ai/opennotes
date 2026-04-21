# frozen_string_literal: true

RSpec.describe OpenNotes::GcpAuth do
  let(:audience) { "https://opennotes-server-bydmv6fnwq-uc.a.run.app" }
  let(:stubs) { Faraday::Adapter::Test::Stubs.new }

  # Match production metadata_connection headers so any contract the SUT places
  # on the default connection (e.g. Metadata-Flavor: Google) is preserved in tests.
  let(:metadata_connection) do
    Faraday.new(url: described_class::METADATA_URL) do |f|
      f.headers["Metadata-Flavor"] = "Google"
      f.adapter :test, stubs
    end
  end

  before do
    described_class.reset_cache!
    allow(described_class).to receive(:metadata_connection).and_return(metadata_connection)

    # Default: K_SERVICE unset so probe path runs. Individual examples override.
    allow(ENV).to receive(:[]).and_call_original
    allow(ENV).to receive(:[]).with("K_SERVICE").and_return(nil)
  end

  after { stubs.verify_stubbed_calls }

  def jwt_with_exp(exp_epoch)
    header = Base64.urlsafe_encode64('{"alg":"RS256","typ":"JWT"}', padding: false)
    payload = Base64.urlsafe_encode64(%({"exp":#{exp_epoch},"aud":"#{audience}"}), padding: false)
    signature = Base64.urlsafe_encode64("sig", padding: false)
    "#{header}.#{payload}.#{signature}"
  end

  describe ".on_gcp?" do
    it "returns true when K_SERVICE env var is set without probing metadata" do
      allow(ENV).to receive(:[]).with("K_SERVICE").and_return("opennotes-server")
      expect(described_class).not_to receive(:probe_metadata_server)
      expect(described_class.on_gcp?).to be true
    end

    it "returns true when metadata server responds" do
      stubs.get("/") { [200, { "Metadata-Flavor" => "Google" }, ""] }
      expect(described_class.on_gcp?).to be true
    end

    it "returns false when metadata server unreachable" do
      stubs.get("/") { raise Faraday::ConnectionFailed, "refused" }
      expect(described_class.on_gcp?).to be false
    end

    it "caches the probe result within the detection TTL" do
      probe_calls = 0
      stubs.get("/") do |_env|
        probe_calls += 1
        [200, {}, ""]
      end
      expect(described_class.on_gcp?).to be true
      expect(described_class.on_gcp?).to be true
      expect(probe_calls).to eq(1)
    end

    it "re-probes after the detection TTL has elapsed" do
      probe_calls = 0
      stubs.get("/") do |_env|
        probe_calls += 1
        [200, {}, ""]
      end

      expect(described_class.on_gcp?).to be true
      # Simulate TTL expiry by moving the probed_at marker into the past.
      described_class.instance_variable_set(
        :@on_gcp_probed_at,
        Time.now.to_i - described_class::DETECTION_TTL_SECONDS - 1,
      )
      expect(described_class.on_gcp?).to be true
      expect(probe_calls).to eq(2)
    end
  end

  describe ".identity_token" do
    it "fetches a token from the metadata server with the requested audience and forwards Metadata-Flavor" do
      expected_path = "#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}"
      token = jwt_with_exp(Time.now.to_i + 3600)

      stubs.get(expected_path) do |env|
        expect(env.request_headers["Metadata-Flavor"]).to eq("Google")
        [200, { "Content-Type" => "text/plain" }, token]
      end

      expect(described_class.identity_token(audience)).to eq(token)
    end

    it "caches the token for the same audience until near expiry" do
      token = jwt_with_exp(Time.now.to_i + 3600)
      call_count = 0

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        call_count += 1
        [200, {}, token]
      end

      2.times { described_class.identity_token(audience) }
      expect(call_count).to eq(1)
    end

    it "refetches when the cached token is inside the refresh buffer" do
      near_expiry = jwt_with_exp(Time.now.to_i + 10)
      fresh = jwt_with_exp(Time.now.to_i + 3600)
      tokens = [near_expiry, fresh]

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [200, {}, tokens.shift]
      end

      expect(described_class.identity_token(audience)).to eq(near_expiry)
      expect(described_class.identity_token(audience)).to eq(fresh)
    end

    it "uses the fallback expiry when the response is not a parseable JWT" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [200, {}, "not-a-jwt"]
      end

      expect(described_class.identity_token(audience)).to eq("not-a-jwt")
      expect(described_class.identity_token(audience)).to eq("not-a-jwt")
    end

    it "uses the fallback expiry when a three-part token has an unparseable payload" do
      malformed =
        "#{Base64.urlsafe_encode64('{"alg":"RS256"}', padding: false)}.not-json.#{Base64.urlsafe_encode64('sig', padding: false)}"

      call_count = 0
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        call_count += 1
        [200, {}, malformed]
      end

      expect(described_class.identity_token(audience)).to eq(malformed)
      # Cache populated with fallback expiry — no second fetch.
      expect(described_class.identity_token(audience)).to eq(malformed)
      expect(call_count).to eq(1)
    end

    it "returns nil and logs the status when the metadata server returns non-2xx" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [403, {}, "forbidden"]
      end

      expect(Rails.logger).to receive(:warn).with(/403/)

      expect(described_class.identity_token(audience)).to be_nil
    end

    it "throttles repeated failure warnings for the same audience to once per WARN_THROTTLE_SECONDS" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [403, {}, "forbidden"]
      end

      expect(Rails.logger).to receive(:warn).with(/403/).once

      3.times { described_class.identity_token(audience) }
    end

    it "returns nil on network error" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        raise Faraday::ConnectionFailed, "refused"
      end

      expect(described_class.identity_token(audience)).to be_nil
    end

    it "keeps separate cache entries per audience" do
      other = "https://other.example.com"
      tok_a = jwt_with_exp(Time.now.to_i + 3600)
      tok_b = jwt_with_exp(Time.now.to_i + 3600)

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") { [200, {}, tok_a] }
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(other)}") { [200, {}, tok_b] }

      expect(described_class.identity_token(audience)).to eq(tok_a)
      expect(described_class.identity_token(other)).to eq(tok_b)
    end

    it "single-flights concurrent refreshes for the same audience (one metadata fetch)" do
      token = jwt_with_exp(Time.now.to_i + 3600)
      call_count = 0
      fetch_entered = Queue.new
      release_fetch = Queue.new
      thread_b_queued = Queue.new

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        call_count += 1
        fetch_entered << :entered
        release_fetch.pop
        [200, {}, token]
      end

      # Instrument the mutex so we get a deterministic "thread_b reached the
      # lock" signal — no wall-clock sleep.
      original_mutex = described_class.send(:token_mutex)
      instrumented = Module.new do
        define_method(:synchronize) do |&block|
          thread_b_queued << :queued if Thread.current[:gcp_auth_spec_role] == :b
          original_mutex.synchronize(&block)
        end
      end
      wrapper = Object.new
      wrapper.extend(instrumented)
      allow(described_class).to receive(:token_mutex).and_return(wrapper)

      thread_a = Thread.new do
        Thread.current[:gcp_auth_spec_role] = :a
        described_class.identity_token(audience)
      end
      fetch_entered.pop # thread_a is inside the metadata fetch, holding the mutex

      thread_b = Thread.new do
        Thread.current[:gcp_auth_spec_role] = :b
        described_class.identity_token(audience)
      end
      thread_b_queued.pop # thread_b has reached synchronize and is blocked on the mutex

      release_fetch << :go
      [thread_a, thread_b].each(&:join)
      expect(call_count).to eq(1)
    end
  end
end
