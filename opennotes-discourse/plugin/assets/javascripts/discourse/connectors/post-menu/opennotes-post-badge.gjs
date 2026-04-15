import Component from "@glimmer/component";
import ConsensusBadge from "../../components/consensus-badge";

export default class OpennotesPostBadge extends Component {
  get status() {
    return this.args.outletArgs?.post?.opennotes_status;
  }

  <template>
    <ConsensusBadge @status={{this.status}} />
  </template>
}
