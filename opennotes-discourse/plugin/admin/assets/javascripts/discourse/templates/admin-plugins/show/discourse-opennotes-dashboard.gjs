import DBreadcrumbsItem from "discourse/components/d-breadcrumbs-item";
import { i18n } from "discourse-i18n";
import OpennotesAdminDashboard from "discourse/plugins/discourse-opennotes/discourse/components/opennotes-admin-dashboard";

export default <template>
  <DBreadcrumbsItem
    @path="/admin/plugins/discourse-opennotes/dashboard"
    @label={{i18n "opennotes.dashboard.title"}}
  />
  <div class="discourse-opennotes__admin-dashboard admin-detail">
    <OpennotesAdminDashboard />
  </div>
</template>
