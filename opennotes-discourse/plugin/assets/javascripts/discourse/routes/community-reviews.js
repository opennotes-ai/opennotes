import DiscourseRoute from "discourse/routes/discourse";
import { ajax } from "discourse/lib/ajax";

export default class CommunityReviewsRoute extends DiscourseRoute {
  model() {
    return ajax("/opennotes/reviews");
  }
}
