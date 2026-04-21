# frozen_string_literal: true

RSpec.describe OpenNotes::GcpAuth do
  let(:audience) { "https://opennotes-server-bydmv6fnwq-uc.a.run.app" }
  let(:stubs) { Faraday::Adapter::Test::Stubs.new }
  let(:metadata_connection) do
    Faraday.new(url: described_class::METADATA_URL) { |f| f.adapter :test, stubs }
  end

  before do
    described_class.reset_cache!
    allow(described_class).to receive(:metadata_connection).and_return(metadata_connection)
  end

  after { stubs.verify_stubbed_calls }

  def jwt_with_exp(exp_epoch)
    header = Base64.urlsafe_encode64('{"alg":"RS256","typ":"JWT"}', padding: false)
    payload = Base64.urlsafe_encode64(%({"exp":#{exp_epoch},"aud":"#{audience}"}), padding: false)
    signature = Base64.urlsafe_encode64("sig", padding: false)
    "#{header}.#{payload}.#{signature}"
  end

  describe ".on_gcp?" do
    it "returns true when K_SERVICE env var is set" do
      stub_const("ENV", ENV.to_h.merge("K_SERVICE" => "opennotes-server"))
      expect(described_class.on_gcp?).to be true
    end

    it "returns true when metadata server responds" do
      stub_const("ENV", ENV.to_h.reject { |k, _| k == "K_SERVICE" })
      stubs.get("/") { [200, { "Metadata-Flavor" => "Google" }, ""] }
      expect(described_class.on_gcp?).to be true
    end

    it "returns false when metadata server unreachable" do
      stub_const("ENV", ENV.to_h.reject { |k, _| k == "K_SERVICE" })
      stubs.get("/") { raise Faraday::ConnectionFailed, "refused" }
      expect(described_class.on_gcp?).to be false
    end

    it "caches detection result" do
      stub_const("ENV", ENV.to_h.merge("K_SERVICE" => "opennotes-server"))
      expect(described_class.on_gcp?).to be true
      stub_const("ENV", ENV.to_h.reject { |k, _| k == "K_SERVICE" })
      expect(described_class.on_gcp?).to be true
    end
  end

  describe ".identity_token" do
    it "fetches and returns a token from metadata server with the requested audience" do
      expected_path = "#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}"
      token = jwt_with_exp(Time.now.to_i + 3600)

      stubs.get(expected_path) do |env|
        expect(env.request_headers["Metadata-Flavor"]).to eq("Google")
        [200, { "Content-Type" => "text/plain" }, token]
      end

      expect(described_class.identity_token(audience)).to eq(token)
    end

    it "caches the token for the same audience until refresh buffer" do
      token = jwt_with_exp(Time.now.to_i + 3600)
      call_count = 0

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        call_count += 1
        [200, { "Content-Type" => "text/plain" }, token]
      end

      2.times { described_class.identity_token(audience) }
      expect(call_count).to eq(1)
    end

    it "refetches when cached token is near expiry" do
      near_expiry = jwt_with_exp(Time.now.to_i + 10)
      fresh = jwt_with_exp(Time.now.to_i + 3600)
      tokens = [near_expiry, fresh]

      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [200, { "Content-Type" => "text/plain" }, tokens.shift]
      end

      expect(described_class.identity_token(audience)).to eq(near_expiry)
      expect(described_class.identity_token(audience)).to eq(fresh)
    end

    it "uses a fallback expiry when token is not a parseable JWT" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [200, { "Content-Type" => "text/plain" }, "not-a-jwt"]
      end

      expect(described_class.identity_token(audience)).to eq("not-a-jwt")
      # Second call uses cache (fallback expiry is far enough in the future)
      expect(described_class.identity_token(audience)).to eq("not-a-jwt")
    end

    it "returns nil when metadata server returns non-2xx" do
      stubs.get("#{described_class::METADATA_PATH}?audience=#{CGI.escape(audience)}") do |_env|
        [403, {}, "forbidden"]
      end

      expect(described_class.identity_token(audience)).to be_nil
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
  end
end
