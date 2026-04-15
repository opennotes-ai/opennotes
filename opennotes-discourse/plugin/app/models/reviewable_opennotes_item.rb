# frozen_string_literal: true

class ReviewableOpennotesItem < Reviewable
  STATES = %i[
    pending
    under_review
    auto_actioned
    retro_review
    consensus_helpful
    consensus_not_helpful
    action_confirmed
    action_overturned
    staff_overridden
    resolved
    restored
    dismissed
  ].freeze

  VALID_TRANSITIONS = {
    pending: %i[under_review auto_actioned retro_review dismissed],
    under_review: %i[consensus_helpful consensus_not_helpful staff_overridden retro_review dismissed],
    auto_actioned: %i[retro_review],
    retro_review: %i[action_confirmed action_overturned staff_overridden],
    consensus_helpful: %i[resolved],
    consensus_not_helpful: %i[resolved],
    action_confirmed: %i[resolved],
    action_overturned: %i[restored],
    staff_overridden: %i[resolved],
    restored: %i[],
    resolved: %i[],
    dismissed: %i[],
  }.freeze

  def self.create_for(post, state:, opennotes_request_id: nil, opennotes_note_id: nil, opennotes_action_id: nil)
    reviewable = new(
      created_by: Discourse.system_user,
      target: post,
      topic: post.topic,
      reviewable_by_moderator: true,
    )
    reviewable.add_score(
      Discourse.system_user,
      ReviewableScore.types[:needs_approval],
      reason: "opennotes_review",
    )
    reviewable.opennotes_request_id = opennotes_request_id
    reviewable.opennotes_note_id = opennotes_note_id
    reviewable.opennotes_action_id = opennotes_action_id
    reviewable.opennotes_state = state.to_s
    reviewable.save!
    reviewable
  end

  def self.find_by_opennotes_request_id(request_id)
    where("payload->>'opennotes_request_id' = ?", request_id).first
  end

  def opennotes_request_id
    payload["opennotes_request_id"]
  end

  def opennotes_request_id=(value)
    self.payload ||= {}
    payload["opennotes_request_id"] = value
  end

  def opennotes_note_id
    payload["opennotes_note_id"]
  end

  def opennotes_note_id=(value)
    self.payload ||= {}
    payload["opennotes_note_id"] = value
  end

  def opennotes_action_id
    payload["opennotes_action_id"]
  end

  def opennotes_action_id=(value)
    self.payload ||= {}
    payload["opennotes_action_id"] = value
  end

  def opennotes_state
    payload["opennotes_state"] || "pending"
  end

  def opennotes_state=(value)
    self.payload ||= {}
    payload["opennotes_state"] = value.to_s
  end

  def transition_to(new_state)
    new_state = new_state.to_sym
    current = opennotes_state.to_sym

    unless VALID_TRANSITIONS[current]&.include?(new_state)
      raise InvalidStateTransition.new(current, new_state)
    end

    self.opennotes_state = new_state
    transition_mutations(new_state)
    update_discourse_status(new_state)
    save!
  end

  def build_actions(actions, guardian, _args)
    return unless pending? || guardian.is_staff?

    if opennotes_state.to_sym.in?(%i[pending under_review consensus_helpful retro_review])
      build_agree_actions(actions, guardian)
    end

    if opennotes_state.to_sym.in?(%i[pending under_review consensus_not_helpful retro_review])
      build_disagree_actions(actions, guardian)
    end

    if opennotes_state.to_sym.in?(%i[pending under_review])
      actions.add(:ignore) do |action|
        action.label = "reviewables.actions.ignore.title"
      end
    end

    if opennotes_state.to_sym.in?(%i[under_review retro_review]) && guardian.is_staff?
      actions.add(:escalate) do |action|
        action.label = "opennotes.reviewable.actions.escalate"
      end
    end
  end

  def perform_agree(performed_by, _args)
    client = self.class.opennotes_client

    if opennotes_note_id
      client.post(
        "/api/v2/notes/#{opennotes_note_id}/force-publish",
        body: {},
        user: performed_by,
      )
    end

    post = target
    OpenNotes::ActionExecutor.hide_post(post) if post

    transition_to(:staff_overridden)
    transition_to(:resolved)

    create_result(:success, :agreed)
  end

  def perform_disagree(performed_by, _args)
    client = self.class.opennotes_client

    if opennotes_note_id
      client.post(
        "/api/v2/notes/#{opennotes_note_id}/dismiss",
        body: {},
        user: performed_by,
      )
    end

    post = target
    OpenNotes::ActionExecutor.unhide_post(post) if post

    transition_to(:staff_overridden)
    transition_to(:resolved)

    create_result(:success, :disagreed)
  end

  def perform_ignore(performed_by, _args)
    client = self.class.opennotes_client

    if opennotes_request_id
      client.delete(
        "/api/v2/requests/#{opennotes_request_id}",
        user: performed_by,
      )
    end

    self.opennotes_state = "dismissed"
    self.status = Reviewable.statuses[:ignored]
    save!

    create_result(:success, :ignored)
  end

  def perform_escalate(performed_by, _args)
    client = self.class.opennotes_client

    if opennotes_request_id
      client.patch(
        "/api/v2/requests/#{opennotes_request_id}",
        body: { data: { attributes: { escalated: true } } },
        user: performed_by,
      )
    end

    self.opennotes_state = "staff_overridden"
    save!

    create_result(:success, :escalated)
  end

  class InvalidStateTransition < StandardError
    def initialize(from, to)
      super("Invalid state transition from #{from} to #{to}")
    end
  end

  private

  def build_agree_actions(actions, _guardian)
    actions.add(:agree) do |action|
      action.label = "reviewables.actions.agree.title"
    end
  end

  def build_disagree_actions(actions, _guardian)
    actions.add(:disagree) do |action|
      action.label = "reviewables.actions.disagree.title"
    end
  end

  def update_discourse_status(new_state)
    case new_state
    when :resolved, :restored
      self.status = Reviewable.statuses[:approved]
    when :dismissed
      self.status = Reviewable.statuses[:ignored]
    when :staff_overridden
      self.status = Reviewable.statuses[:rejected]
    end
  end

  def transition_mutations(new_state)
    self.payload ||= {}
    case new_state
    when :consensus_helpful
      payload["consensus_type"] = "helpful"
    when :consensus_not_helpful
      payload["consensus_type"] = "not_helpful"
    end
  end

  def self.opennotes_client
    OpenNotes::Client.new(
      server_url: SiteSetting.opennotes_server_url,
      api_key: SiteSetting.opennotes_api_key,
    )
  end
end
