import {
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
  Link,
} from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/LoginPage";
import { OverviewPage } from "@/pages/OverviewPage";
import { AppsListPage } from "@/pages/AppsListPage";
import { AppDetailPage } from "@/pages/AppDetailPage";
import { FindingsPage } from "@/pages/FindingsPage";
import { RunsPage } from "@/pages/RunsPage";
import { AccountPage } from "@/pages/AccountPage";
import { ErrorBoundary } from "@/components/ErrorBoundary";

function NotFound() {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="text-6xl font-bold text-slate-700 mb-2">404</div>
      <h2 className="text-xl font-semibold text-slate-100 mb-2">
        Stránka sa nenašla
      </h2>
      <p className="text-sm text-slate-400 max-w-sm mb-6">
        Požadovaná stránka neexistuje alebo bola presunutá na inú adresu.
      </p>
      <Link
        to="/"
        className="px-4 py-2 text-sm font-medium rounded-lg bg-sky-600 hover:bg-sky-500 text-white shadow-sm transition"
      >
        Návrat na prehľad
      </Link>
    </div>
  );
}

function AuthGate() {
  const queryClient = useQueryClient();

  const me = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });

  useEffect(() => {
    const handleUnauthorized = () => {
      queryClient.setQueryData(["me"], null);
      queryClient.invalidateQueries({ queryKey: ["me"] });
    };

    window.addEventListener("straz:unauthorized", handleUnauthorized);
    return () => {
      window.removeEventListener("straz:unauthorized", handleUnauthorized);
    };
  }, [queryClient]);

  if (me.isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-4">
        <div className="flex flex-col items-center gap-4">
          <div className="relative flex items-center justify-center w-12 h-12">
            <div className="absolute inset-0 rounded-full border-2 border-sky-500/20" />
            <div className="w-12 h-12 rounded-full border-2 border-sky-400 border-t-transparent animate-spin" />
          </div>
          <div className="text-xs font-medium text-slate-400 tracking-wider uppercase">
            Overujem reláciu…
          </div>
        </div>
      </div>
    );
  }

  if (me.isError || !me.data) {
    return (
      <LoginPage
        onSuccess={() => {
          void me.refetch();
        }}
      />
    );
  }

  return (
    <ErrorBoundary>
      <Outlet />
    </ErrorBoundary>
  );
}

const rootRoute = createRootRoute({
  component: AuthGate,
  notFoundComponent: NotFound,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => (
    <ErrorBoundary>
      <OverviewPage />
    </ErrorBoundary>
  ),
});

const appsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apps",
  component: () => (
    <ErrorBoundary>
      <AppsListPage />
    </ErrorBoundary>
  ),
});

const appDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/apps/$appId",
  component: () => (
    <ErrorBoundary>
      <AppDetailPage />
    </ErrorBoundary>
  ),
});

const findingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/findings",
  component: () => (
    <ErrorBoundary>
      <FindingsPage />
    </ErrorBoundary>
  ),
});

const runsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/runs",
  component: () => (
    <ErrorBoundary>
      <RunsPage />
    </ErrorBoundary>
  ),
});

const accountRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/account",
  component: function Account() {
    return (
      <ErrorBoundary>
        <AccountPage
          onLogout={() => {
            window.location.href = "/";
          }}
        />
      </ErrorBoundary>
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
  defaultNotFoundComponent: NotFound,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
