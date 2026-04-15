# frozen_string_literal: true

require "rails_helper"

RSpec.describe "discourse-opennotes plugin hooks" do
  fab!(:parent_category) { Fabricate(:category, slug: "gaming") }
  fab!(:child_category) { Fabricate(:category, slug: "disputes", parent_category: parent_category) }
  fab!(:unmonitored_category) { Fabricate(:category, slug: "off-topic") }
  fab!(:user) { Fabricate(:admin) }
  fab!(:flagger) { Fabricate(:user, trust_level: 2) }

  before do
    SiteSetting.opennotes_enabled = true
    SiteSetting.opennotes_server_url = "https://opennotes.example.com"
    SiteSetting.opennotes_api_key = "test-api-key"
    SiteSetting.opennotes_monitored_categories = "gaming/disputes"
    SiteSetting.opennotes_route_flags_to_community = true
  end

  describe ":post_created event with nested categories" do
    it "enqueues sync job for posts in monitored subcategory" do
      expect {
        PostCreator.create!(user, title: "Test topic in disputes", raw: "This is a test post in the monitored disputes subcategory.", category: child_category.id)
      }.to change { Jobs::SyncPostToOpennotes.jobs.size }.by(1)
    end

    it "does not enqueue sync job for posts in unmonitored category" do
      expect {
        PostCreator.create!(user, title: "Off topic post here", raw: "This is a test post in an unmonitored category.", category: unmonitored_category.id)
      }.not_to change { Jobs::SyncPostToOpennotes.jobs.size }
    end

    it "matches parent-only slug path for top-level category" do
      SiteSetting.opennotes_monitored_categories = "gaming"

      expect {
        PostCreator.create!(user, title: "Test post in parent", raw: "This is a test post directly in the parent gaming category.", category: parent_category.id)
      }.to change { Jobs::SyncPostToOpennotes.jobs.size }.by(1)
    end
  end
end
