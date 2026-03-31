import Component from "@glimmer/component";
import I18n from "discourse-i18n";

export default class OpennotesReviewBanner extends Component {
  get status() {
    return this.args.outletArgs?.model?.opennotes_status;
  }

  get shouldShow() {
    return this.status === "under_review" || this.status === "auto_actioned";
  }

  get bannerClass() {
    return this.status === "auto_actioned"
      ? "opennotes-review-banner--danger"
      : "opennotes-review-banner--warning";
  }

  get bannerText() {
    return this.status === "auto_actioned"
      ? I18n.t("opennotes.banner.auto_actioned")
      : I18n.t("opennotes.banner.under_review");
  }

  <template>
    {{#if this.shouldShow}}
      <div class="opennotes-review-banner {{this.bannerClass}}">
        {{this.bannerText}}
      </div>
    {{/if}}
  </template>
}
