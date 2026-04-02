import Component from "@glimmer/component";
import { tracked } from "@glimmer/tracking";
import { action } from "@ember/object";
import { inject as service } from "@ember/service";
import I18n from "discourse-i18n";
import { ajax } from "discourse/lib/ajax";

export default class OpennotesAdminDashboard extends Component {
  @service siteSettings;

  @tracked data = null;
  @tracked loading = true;
  @tracked error = null;

  constructor() {
    super(...arguments);
    this.loadDashboard();
  }

  @action
  async loadDashboard() {
    this.loading = true;
    this.error = null;

    try {
      this.data = await ajax("/admin/plugins/opennotes/dashboard.json");
    } catch (e) {
      this.error = I18n.t("opennotes.dashboard.error");
    } finally {
      this.loading = false;
    }
  }

  get activityMetrics() {
    return this.data?.activity;
  }

  get classificationBreakdown() {
    return this.data?.classification;
  }

  get consensusHealth() {
    return this.data?.consensus;
  }

  get topReviewers() {
    return this.data?.top_reviewers;
  }

  <template>
    <div class="opennotes-admin-dashboard">
      <h1>{{I18n.t "opennotes.dashboard.title"}}</h1>

      {{#if this.loading}}
        <div class="opennotes-admin-dashboard__loading">
          {{I18n.t "opennotes.dashboard.loading"}}
        </div>
      {{else if this.error}}
        <div class="opennotes-admin-dashboard__error">
          {{this.error}}
        </div>
      {{else}}
        <section class="opennotes-admin-dashboard__section">
          <h2>{{I18n.t "opennotes.dashboard.activity"}}</h2>
          {{#if this.activityMetrics}}
            <table class="opennotes-admin-dashboard__table">
              <tbody>
                {{#each-in this.activityMetrics as |key value|}}
                  <tr>
                    <td>{{key}}</td>
                    <td>{{value}}</td>
                  </tr>
                {{/each-in}}
              </tbody>
            </table>
          {{/if}}
        </section>

        <section class="opennotes-admin-dashboard__section">
          <h2>{{I18n.t "opennotes.dashboard.classification"}}</h2>
          {{#if this.classificationBreakdown}}
            <table class="opennotes-admin-dashboard__table">
              <tbody>
                {{#each-in this.classificationBreakdown as |key value|}}
                  <tr>
                    <td>{{key}}</td>
                    <td>{{value}}</td>
                  </tr>
                {{/each-in}}
              </tbody>
            </table>
          {{/if}}
        </section>

        <section class="opennotes-admin-dashboard__section">
          <h2>{{I18n.t "opennotes.dashboard.consensus"}}</h2>
          {{#if this.consensusHealth}}
            <table class="opennotes-admin-dashboard__table">
              <tbody>
                {{#each-in this.consensusHealth as |key value|}}
                  <tr>
                    <td>{{key}}</td>
                    <td>{{value}}</td>
                  </tr>
                {{/each-in}}
              </tbody>
            </table>
          {{/if}}
        </section>

        <section class="opennotes-admin-dashboard__section">
          <h2>{{I18n.t "opennotes.dashboard.top_reviewers"}}</h2>
          {{#if this.topReviewers}}
            <table class="opennotes-admin-dashboard__table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Reviews</th>
                  <th>Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {{#each this.topReviewers as |reviewer|}}
                  <tr>
                    <td>{{reviewer.username}}</td>
                    <td>{{reviewer.review_count}}</td>
                    <td>{{reviewer.accuracy}}</td>
                  </tr>
                {{/each}}
              </tbody>
            </table>
          {{/if}}
        </section>
      {{/if}}
    </div>
  </template>
}
