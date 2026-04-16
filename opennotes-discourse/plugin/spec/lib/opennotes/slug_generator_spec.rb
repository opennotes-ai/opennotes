# frozen_string_literal: true

require "rails_helper"

RSpec.describe OpenNotes::SlugGenerator do
  describe ".generate" do
    it "returns hostname-hex8 format for non-blank email" do
      slug = described_class.generate(hostname: "forum.example.com", contact_email: "admin@example.com")
      expect(slug).to match(/\Aforum\.example\.com-[0-9a-f]{8}\z/)
    end

    it "is deterministic: same inputs produce the same slug" do
      a = described_class.generate(hostname: "forum.example.com", contact_email: "admin@example.com")
      b = described_class.generate(hostname: "forum.example.com", contact_email: "admin@example.com")
      expect(a).to eq(b)
    end

    it "produces different suffixes for different emails on the same hostname" do
      a = described_class.generate(hostname: "forum.example.com", contact_email: "a@example.com")
      b = described_class.generate(hostname: "forum.example.com", contact_email: "b@example.com")
      expect(a).not_to eq(b)
    end

    it "uses hostname-only fallback when contact_email is blank" do
      slug = described_class.generate(hostname: "forum.example.com", contact_email: "")
      expect(slug).to eq("forum.example.com")
    end

    it "uses hostname-only fallback when contact_email is nil" do
      slug = described_class.generate(hostname: "forum.example.com", contact_email: nil)
      expect(slug).to eq("forum.example.com")
    end

    it "caps output at 255 characters" do
      long_host = "a" * 300
      slug = described_class.generate(hostname: long_host, contact_email: "admin@example.com")
      expect(slug.length).to eq(255)
    end

    it "uses lowercase hex characters only in suffix" do
      slug = described_class.generate(hostname: "h", contact_email: "x@y.z")
      suffix = slug.split("-").last
      expect(suffix).to match(/\A[0-9a-f]{8}\z/)
    end

    it "does not embed raw email local-part in the slug (privacy)" do
      slug = described_class.generate(hostname: "forum.example.com", contact_email: "secret@mail.com")
      expect(slug).not_to include("secret")
      expect(slug).not_to include("@")
    end
  end

  describe ".generate_for_site" do
    it "reads hostname and contact_email from Discourse/SiteSetting" do
      allow(Discourse).to receive(:current_hostname).and_return("forum.test")
      allow(SiteSetting).to receive(:contact_email).and_return("admin@test.com")
      expect(described_class.generate_for_site).to match(/\Aforum\.test-[0-9a-f]{8}\z/)
    end

    it "falls back to hostname when contact_email is blank and logs a warning" do
      allow(Discourse).to receive(:current_hostname).and_return("forum.test")
      allow(SiteSetting).to receive(:contact_email).and_return("")
      expect(Rails.logger).to receive(:warn).with(/contact_email blank/i)
      expect(described_class.generate_for_site).to eq("forum.test")
    end
  end
end
