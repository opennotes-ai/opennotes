import { withPluginApi } from "discourse/lib/plugin-api";

const PLUGIN_ID = "discourse-opennotes";

export default {
  name: "opennotes-admin-plugin-configuration-nav",

  initialize(container) {
    const currentUser = container.lookup("service:current-user");
    if (!currentUser?.admin) {
      return;
    }

    withPluginApi((api) => {
      api.setAdminPluginIcon(PLUGIN_ID, "file-lines");
      api.addAdminPluginConfigurationNav(PLUGIN_ID, [
        {
          label: "opennotes.admin.dashboard",
          route: "adminPlugins.show.discourse-opennotes-dashboard",
        },
      ]);
    });
  },
};
