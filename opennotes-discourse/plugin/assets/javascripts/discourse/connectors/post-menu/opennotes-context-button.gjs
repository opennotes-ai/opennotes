import Component from "@glimmer/component";
import I18n from "discourse-i18n";

export default class OpennotesContextButton extends Component {
  get status() {
    return this.args.outletArgs?.post?.opennotes_status;
  }

  get shouldShow() {
    return (
      this.status === "resolved_helpful" ||
      this.status === "resolved_not_helpful"
    );
  }

  get badgeClass() {
    return this.status === "resolved_helpful"
      ? "opennotes-badge--helpful"
      : "opennotes-badge--no-action";
  }

  get badgeText() {
    return this.status === "resolved_helpful"
      ? I18n.t("opennotes.badge.community_reviewed")
      : I18n.t("opennotes.badge.no_action");
  }

  <template>
    {{#if this.shouldShow}}
      <span class="opennotes-badge {{this.badgeClass}}">
        {{this.badgeText}}
      </span>
    {{/if}}
  </template>
}
