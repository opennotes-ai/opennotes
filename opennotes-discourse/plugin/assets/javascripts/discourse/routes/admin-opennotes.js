import DiscourseRoute from "discourse/routes/discourse";
import { ajax } from "discourse/lib/ajax";

export default class AdminOpennotesRoute extends DiscourseRoute {
  model() {
    return ajax("/admin/plugins/opennotes/dashboard.json");
  }
}
