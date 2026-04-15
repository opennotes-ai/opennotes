import Component from "@glimmer/component";
import I18n from "discourse-i18n";

const BANNER_CONFIG = {
  under_review: {
    className: "opennotes-review-banner--warning",
    i18nKey: "opennotes.banner.under_review",
  },
  auto_actioned: {
    className: "opennotes-review-banner--danger",
    i18nKey: "opennotes.banner.auto_actioned",
  },
  retro_review: {
    className: "opennotes-review-banner--danger",
    i18nKey: "opennotes.banner.auto_actioned",
  },
};

export default class OpennotesReviewBanner extends Component {
  get status() {
    return this.args.outletArgs?.model?.opennotes_status;
  }

  get config() {
    return BANNER_CONFIG[this.status];
  }

  get shouldShow() {
    return !!this.config;
  }

  get bannerClass() {
    return this.config?.className;
  }

  get bannerText() {
    return this.config ? I18n.t(this.config.i18nKey) : "";
  }

  <template>
    {{#if this.shouldShow}}
      <div class="opennotes-review-banner {{this.bannerClass}}">
        {{this.bannerText}}
      </div>
    {{/if}}
  </template>
}
