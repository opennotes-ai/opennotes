# frozen_string_literal: true

RSpec.describe OpenNotes::PostMapper do
  let(:category) do
    instance_double("Category", id: 5, name: "General Discussion")
  end

  let(:topic) do
    instance_double("Topic", title: "Is this claim true?", category: category, id: 100)
  end

  let(:post_user) do
    instance_double("User", id: 42, username: "alice", trust_level: 2)
  end

  let(:post) do
    instance_double(
      "Post",
      id: 789,
      raw: "This is the post content that needs review.",
      topic: topic,
      topic_id: 100,
      user: post_user,
      post_number: 3,
      created_at: Time.utc(2026, 3, 15, 10, 30, 0),
    )
  end

  let(:community_server_id) { "abc-123-def" }

  describe ".to_request" do
    it "returns a JSON:API formatted payload" do
      result = described_class.to_request(post, community_server_id: community_server_id)

      expect(result[:data][:type]).to eq("requests")
      expect(result[:data][:attributes]).to be_a(Hash)
    end

    it "maps post content to original_message_content" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:original_message_content]).to eq("This is the post content that needs review.")
    end

    it "uses the correct request_id format" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:request_id]).to eq("discourse-post-789")
    end

    it "includes the community_server_id" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:community_server_id]).to eq("abc-123-def")
    end

    it "maps platform identifiers" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:platform_message_id]).to eq("789")
      expect(attrs[:platform_channel_id]).to eq("5")
      expect(attrs[:platform_author_id]).to eq("42")
      expect(attrs[:requested_by]).to eq("42")
    end

    it "includes platform_timestamp as ISO 8601" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:platform_timestamp]).to eq("2026-03-15T10:30:00Z")
    end

    it "includes metadata with topic and author details" do
      result = described_class.to_request(post, community_server_id: community_server_id)
      metadata = result[:data][:attributes][:metadata]

      expect(metadata[:title]).to eq("Is this claim true?")
      expect(metadata[:category]).to eq("General Discussion")
      expect(metadata[:author_username]).to eq("alice")
      expect(metadata[:author_trust_level]).to eq(2)
      expect(metadata[:post_number]).to eq(3)
      expect(metadata[:topic_id]).to eq(100)
    end

    it "handles posts without a category" do
      allow(topic).to receive(:category).and_return(nil)

      result = described_class.to_request(post, community_server_id: community_server_id)
      attrs = result[:data][:attributes]

      expect(attrs[:platform_channel_id]).to be_nil
      expect(attrs[:metadata][:category]).to be_nil
    end
  end

  describe ".to_classification_payload" do
    it "returns the post content" do
      result = described_class.to_classification_payload(post)

      expect(result[:content]).to eq("This is the post content that needs review.")
    end

    it "includes the platform identifier" do
      result = described_class.to_classification_payload(post)

      expect(result[:platform]).to eq("discourse")
      expect(result[:platform_message_id]).to eq("789")
    end

    it "includes metadata" do
      result = described_class.to_classification_payload(post)

      expect(result[:metadata][:title]).to eq("Is this claim true?")
      expect(result[:metadata][:category]).to eq("General Discussion")
      expect(result[:metadata][:author_username]).to eq("alice")
    end
  end
end
