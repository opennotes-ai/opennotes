import Component from "@glimmer/component";
import { tracked } from "@glimmer/tracking";
import { action } from "@ember/object";
import { ajax } from "discourse/lib/ajax";
import I18n from "discourse-i18n";
import VoteWidget from "./vote-widget";

export default class CommunityReviewPanel extends Component {
  @tracked items = [];
  @tracked isLoading = true;

  constructor() {
    super(...arguments);
    this.loadItems();
  }

  @action
  async loadItems() {
    this.isLoading = true;
    try {
      const result = await ajax("/opennotes/reviews");
      this.items = result.data ?? [];
    } finally {
      this.isLoading = false;
    }
  }

  <template>
    <div class="opennotes-review-panel">
      <h2 class="opennotes-review-panel__title">
        {{I18n.t "opennotes.review.title"}}
      </h2>

      {{#if this.isLoading}}
        <div class="opennotes-review-panel__loading">
          {{I18n.t "opennotes.review.loading"}}
        </div>
      {{else if this.items.length}}
        <ul class="opennotes-review-panel__list">
          {{#each this.items as |item|}}
            <li class="opennotes-review-panel__item">
              <div class="opennotes-review-panel__item-content">
                <p class="opennotes-review-panel__item-text">{{item.raw}}</p>
                <div class="opennotes-review-panel__item-meta">
                  <span class="opennotes-review-panel__item-category">
                    {{I18n.t "opennotes.review.post_in" category=item.category_name}}
                  </span>
                  <span class="opennotes-review-panel__item-reason">
                    {{I18n.t "opennotes.review.flagged_for" reason=item.reason}}
                  </span>
                  <time class="opennotes-review-panel__item-date">{{item.created_at}}</time>
                </div>
              </div>
              <div class="opennotes-review-panel__item-actions">
                <VoteWidget
                  @noteId={{item.id}}
                  @hasVoted={{item.has_voted}}
                  @userVote={{item.user_vote}}
                  @disabled={{false}}
                />
              </div>
            </li>
          {{/each}}
        </ul>
      {{else}}
        <div class="opennotes-review-panel__empty">
          {{I18n.t "opennotes.review.empty"}}
        </div>
      {{/if}}
    </div>
  </template>
}
