import Component from "@glimmer/component";
import { tracked } from "@glimmer/tracking";
import { action } from "@ember/object";
import { on } from "@ember/modifier";
import { fn } from "@ember/helper";
import { ajax } from "discourse/lib/ajax";
import I18n from "discourse-i18n";

export default class VoteWidget extends Component {
  @tracked isVoting = false;
  @tracked hasVoted = this.args.hasVoted ?? false;
  @tracked selectedVote = this.args.userVote ?? null;

  get isDisabled() {
    return this.isVoting || this.args.disabled || this.hasVoted;
  }

  @action
  async vote(level) {
    if (this.isDisabled) {
      return;
    }

    this.isVoting = true;
    try {
      await ajax(`/opennotes/reviews/${this.args.noteId}/rate`, {
        type: "POST",
        data: { helpfulness_level: level },
      });
      this.hasVoted = true;
      this.selectedVote = level;
    } finally {
      this.isVoting = false;
    }
  }

  <template>
    <div class="opennotes-vote-widget">
      {{#if this.hasVoted}}
        <span class="opennotes-vote-widget__voted">
          {{I18n.t "opennotes.vote.voted" choice=this.selectedVote}}
        </span>
      {{else if this.isVoting}}
        <span class="opennotes-vote-widget__submitting">
          {{I18n.t "opennotes.vote.submitting"}}
        </span>
      {{else}}
        <button
          {{on "click" (fn this.vote "HELPFUL")}}
          disabled={{this.isDisabled}}
          class="btn btn-primary btn-small opennotes-vote-widget__btn opennotes-vote-widget__btn--helpful"
        >
          {{I18n.t "opennotes.vote.helpful"}}
        </button>
        <button
          {{on "click" (fn this.vote "SOMEWHAT_HELPFUL")}}
          disabled={{this.isDisabled}}
          class="btn btn-default btn-small opennotes-vote-widget__btn opennotes-vote-widget__btn--somewhat"
        >
          {{I18n.t "opennotes.vote.somewhat_helpful"}}
        </button>
        <button
          {{on "click" (fn this.vote "NOT_HELPFUL")}}
          disabled={{this.isDisabled}}
          class="btn btn-danger btn-small opennotes-vote-widget__btn opennotes-vote-widget__btn--not-helpful"
        >
          {{I18n.t "opennotes.vote.not_helpful"}}
        </button>
      {{/if}}
    </div>
  </template>
}
