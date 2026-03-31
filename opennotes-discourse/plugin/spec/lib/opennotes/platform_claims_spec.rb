# frozen_string_literal: true

require "jwt"

RSpec.describe OpenNotes::PlatformClaims do
  let(:user) do
    instance_double(
      "User",
      id: 42,
      username: "alice",
      trust_level: 2,
      admin?: false,
      moderator?: false,
    )
  end

  let(:secret) { "test-jwt-secret" }

  before do
    allow(Discourse).to receive(:current_hostname).and_return("community.example.com")
  end

  describe ".claims_for" do
    it "returns platform claims hash for the user" do
      claims = described_class.claims_for(user)

      expect(claims).to eq(
        platform: "discourse",
        scope: "community.example.com",
        sub: "42",
        username: "alice",
        trust_level: 2,
        admin: false,
        moderator: false,
      )
    end

    it "reflects admin and moderator status" do
      admin_user = instance_double(
        "User",
        id: 1,
        username: "admin",
        trust_level: 4,
        admin?: true,
        moderator?: true,
      )

      claims = described_class.claims_for(admin_user)

      expect(claims[:admin]).to be true
      expect(claims[:moderator]).to be true
      expect(claims[:trust_level]).to eq(4)
    end
  end

  describe ".sign" do
    it "returns a valid JWT token" do
      token = described_class.sign(user: user, secret: secret)
      decoded = JWT.decode(token, secret, true, algorithm: "HS256").first

      expect(decoded["platform"]).to eq("discourse")
      expect(decoded["sub"]).to eq("42")
      expect(decoded["username"]).to eq("alice")
      expect(decoded["trust_level"]).to eq(2)
      expect(decoded["admin"]).to be false
      expect(decoded["moderator"]).to be false
    end

    it "includes iat and exp claims" do
      freeze_time = Time.now
      allow(Time).to receive(:now).and_return(freeze_time)

      token = described_class.sign(user: user, secret: secret)
      decoded = JWT.decode(token, secret, true, algorithm: "HS256").first

      expect(decoded["iat"]).to eq(freeze_time.to_i)
      expect(decoded["exp"]).to eq(freeze_time.to_i + 3600)
    end

    it "uses the default scope from Discourse hostname" do
      token = described_class.sign(user: user, secret: secret)
      decoded = JWT.decode(token, secret, true, algorithm: "HS256").first

      expect(decoded["scope"]).to eq("community.example.com")
    end

    it "allows overriding scope" do
      token = described_class.sign(user: user, scope: "other.example.com", secret: secret)
      decoded = JWT.decode(token, secret, true, algorithm: "HS256").first

      expect(decoded["scope"]).to eq("other.example.com")
    end

    it "uses HS256 algorithm" do
      token = described_class.sign(user: user, secret: secret)
      header = JWT.decode(token, secret, true, algorithm: "HS256").last

      expect(header["alg"]).to eq("HS256")
    end

    it "cannot be decoded with a wrong secret" do
      token = described_class.sign(user: user, secret: secret)

      expect {
        JWT.decode(token, "wrong-secret", true, algorithm: "HS256")
      }.to raise_error(JWT::VerificationError)
    end
  end
end
