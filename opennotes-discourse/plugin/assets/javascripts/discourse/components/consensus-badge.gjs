import Component from "@glimmer/component";
import I18n from "discourse-i18n";

const STATUS_CONFIG = {
  helpful: {
    className: "opennotes-badge--helpful",
    i18nKey: "opennotes.badge.community_reviewed",
  },
  not_helpful: {
    className: "opennotes-badge--no-action",
    i18nKey: "opennotes.badge.no_action",
  },
  under_review: {
    className: "opennotes-badge--under-review",
    i18nKey: "opennotes.badge.under_review",
  },
  auto_actioned: {
    className: "opennotes-badge--auto-actioned",
    i18nKey: "opennotes.badge.auto_actioned",
  },
  retro_review: {
    className: "opennotes-badge--auto-actioned",
    i18nKey: "opennotes.badge.auto_actioned",
  },
};

export default class ConsensusBadge extends Component {
  get config() {
    return STATUS_CONFIG[this.args.status];
  }

  get shouldShow() {
    return !!this.config;
  }

  get badgeClass() {
    return this.config?.className;
  }

  get badgeText() {
    return this.config ? I18n.t(this.config.i18nKey) : "";
  }

  <template>
    {{#if this.shouldShow}}
      <span class="opennotes-badge {{this.badgeClass}}">
        {{this.badgeText}}
      </span>
    {{/if}}
  </template>
}
