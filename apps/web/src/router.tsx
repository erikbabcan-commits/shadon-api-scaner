import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/LoginPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { AppsListPage } from "@/pages/AppsListPage";
import { AppDetailPage } from "@/pages/AppDetailPage";
import { FindingsPage } from "@/pages/FindingsPage";
import { RunsPage } from "@/pages/RunsPage";
import { AccountPage } from "@/pages/AccountPage";

function AuthGate() {
  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  if (me.isLoading) {
    return (
      <div className="app-shell" style={{ alignItems: "center", justifyContent: "center" }}>
        Načítavam…
      </div>
    );
  }

  if (me.isError) {
    return (
      <LoginPage
        onSuccess={() => {
          void me.refetch();
        }}
      />
    );
  }

  return <Outlet />;
}

const rootRoute = createRootRoute({
  component: AuthGate,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: OverviewPage,
});

const appsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apps",
  component: AppsListPage,
});

const appDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apps/$appId",
  component: AppDetailPage,
});

const findingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/findings",
  component: FindingsPage,
});

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs",
  component: RunsPage,
});

const accountRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: function Account() {
    return (
      <AccountPage
        onLogout={() => {
          window.location.href = "/";
        }}
      />
    );
  },
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  appsRoute,
  appDetailRoute,
  findingsRoute,
  runsRoute,
  accountRoute,
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
