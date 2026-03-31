import DiscourseRoute from "discourse/routes/discourse";

export default class CommunityReviewsRoute extends DiscourseRoute {
  model() {
    return this.store.ajax("/opennotes/reviews");
  }
}
