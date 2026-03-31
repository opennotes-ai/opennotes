# frozen_string_literal: true

require "rails_helper"

RSpec.describe OpenNotes::ActionExecutor do
  let(:post_record) { Fabricate(:post) }
  let(:system_user) { Discourse.system_user }

  describe ".execute_action" do
    it "dispatches hide_post action" do
      expect(described_class).to receive(:hide_post).with(post_record, reason: :spam)
      described_class.execute_action(action_type: "hide_post", post: post_record)
    end

    it "dispatches unhide_post action" do
      expect(described_class).to receive(:unhide_post).with(post_record)
      described_class.execute_action(action_type: "unhide_post", post: post_record)
    end

    it "dispatches add_staff_annotation action" do
      expect(described_class).to receive(:add_staff_annotation).with(post_record, text: "test annotation")
      described_class.execute_action(
        action_type: "add_staff_annotation",
        post: post_record,
        metadata: { text: "test annotation" },
      )
    end

    it "dispatches set_scan_exempt action" do
      expect(described_class).to receive(:set_scan_exempt).with(post_record, content_hash: "abc123")
      described_class.execute_action(
        action_type: "set_scan_exempt",
        post: post_record,
        metadata: { content_hash: "abc123" },
      )
    end

    it "dispatches clear_scan_exempt action" do
      expect(described_class).to receive(:clear_scan_exempt).with(post_record)
      described_class.execute_action(action_type: "clear_scan_exempt", post: post_record)
    end

    it "logs a warning for unknown action types" do
      expect(Rails.logger).to receive(:warn).with("[opennotes] Unknown action type: bogus_action")
      described_class.execute_action(action_type: "bogus_action", post: post_record)
    end

    it "passes custom reason to hide_post" do
      expect(described_class).to receive(:hide_post).with(post_record, reason: :inappropriate)
      described_class.execute_action(
        action_type: "hide_post",
        post: post_record,
        metadata: { reason: :inappropriate },
      )
    end
  end

  describe ".hide_post" do
    it "creates a PostAction with the spam type" do
      expect(PostAction).to receive(:act).with(
        system_user,
        post_record,
        PostActionType.types[:spam],
      )
      described_class.hide_post(post_record, reason: :spam)
    end

    it "creates a PostAction with the inappropriate type" do
      expect(PostAction).to receive(:act).with(
        system_user,
        post_record,
        PostActionType.types[:inappropriate],
      )
      described_class.hide_post(post_record, reason: :inappropriate)
    end

    it "creates a PostAction with the off_topic type" do
      expect(PostAction).to receive(:act).with(
        system_user,
        post_record,
        PostActionType.types[:off_topic],
      )
      described_class.hide_post(post_record, reason: :off_topic)
    end

    it "defaults to spam for unrecognized reasons" do
      expect(PostAction).to receive(:act).with(
        system_user,
        post_record,
        PostActionType.types[:spam],
      )
      described_class.hide_post(post_record, reason: :unknown_reason)
    end

    it "skips if the post is already hidden" do
      allow(post_record).to receive(:hidden?).and_return(true)
      expect(PostAction).not_to receive(:act)
      described_class.hide_post(post_record)
    end
  end

  describe ".unhide_post" do
    before { allow(post_record).to receive(:hidden?).and_return(true) }

    it "unhides the post and removes the spam PostAction" do
      expect(post_record).to receive(:unhide!)
      expect(PostAction).to receive(:remove_act).with(
        system_user,
        post_record,
        PostActionType.types[:spam],
      )
      described_class.unhide_post(post_record)
    end

    it "still unhides even if remove_act raises" do
      expect(post_record).to receive(:unhide!)
      expect(PostAction).to receive(:remove_act).and_raise(StandardError.new("no action to remove"))
      expect(Rails.logger).to receive(:warn).with(/Error removing post action during unhide/)
      described_class.unhide_post(post_record)
    end

    it "skips if the post is not hidden" do
      allow(post_record).to receive(:hidden?).and_return(false)
      expect(post_record).not_to receive(:unhide!)
      described_class.unhide_post(post_record)
    end
  end

  describe ".add_staff_annotation" do
    let(:topic) { post_record.topic }

    it "creates a whisper moderator post on the topic" do
      expect(topic).to receive(:add_moderator_post).with(
        system_user,
        "Test annotation text",
        post_type: Post.types[:whisper],
      )
      described_class.add_staff_annotation(post_record, text: "Test annotation text")
    end

    it "does nothing when text is nil" do
      expect(topic).not_to receive(:add_moderator_post)
      described_class.add_staff_annotation(post_record, text: nil)
    end

    it "does nothing when text is empty string" do
      expect(topic).not_to receive(:add_moderator_post)
      described_class.add_staff_annotation(post_record, text: "")
    end
  end

  describe ".set_scan_exempt" do
    it "stores scan exempt flag and content hash in post custom fields" do
      described_class.set_scan_exempt(post_record, content_hash: "sha256hashvalue")

      post_record.reload
      expect(post_record.custom_fields[described_class::SCAN_EXEMPT_FIELD]).to eq(true)
      expect(post_record.custom_fields[described_class::SCAN_EXEMPT_HASH_FIELD]).to eq("sha256hashvalue")
    end
  end

  describe ".clear_scan_exempt" do
    it "removes scan exempt flag and content hash from post custom fields" do
      post_record.custom_fields[described_class::SCAN_EXEMPT_FIELD] = true
      post_record.custom_fields[described_class::SCAN_EXEMPT_HASH_FIELD] = "oldhash"
      post_record.save_custom_fields

      described_class.clear_scan_exempt(post_record)

      post_record.reload
      expect(post_record.custom_fields[described_class::SCAN_EXEMPT_FIELD]).to be_nil
      expect(post_record.custom_fields[described_class::SCAN_EXEMPT_HASH_FIELD]).to be_nil
    end
  end

  describe ".scan_exempt?" do
    it "returns true when scan exempt flag is set" do
      post_record.custom_fields[described_class::SCAN_EXEMPT_FIELD] = true
      post_record.save_custom_fields

      expect(described_class.scan_exempt?(post_record)).to be true
    end

    it "returns false when scan exempt flag is not set" do
      expect(described_class.scan_exempt?(post_record)).to be false
    end
  end

  describe ".scan_exempt_hash" do
    it "returns the stored content hash" do
      post_record.custom_fields[described_class::SCAN_EXEMPT_HASH_FIELD] = "testhash123"
      post_record.save_custom_fields

      expect(described_class.scan_exempt_hash(post_record)).to eq("testhash123")
    end

    it "returns nil when no hash is stored" do
      expect(described_class.scan_exempt_hash(post_record)).to be_nil
    end
  end
end
